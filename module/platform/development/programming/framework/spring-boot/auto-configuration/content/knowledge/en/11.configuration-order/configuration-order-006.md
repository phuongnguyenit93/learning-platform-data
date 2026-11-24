# Distinguishing Auto-Configuration Ordering from `@Order`, `Ordered`, and `@DependsOn` in Spring Boot

## 1. Why are there multiple "order" concepts?

In Spring Boot, saying "A must run before B" is not clear enough. Are A and B **two auto-configuration classes**, **two beans placed into a list**, or **two beans being initialized**? Each question uses a different mechanism:

1. **Auto-configuration processing order**: Spring Boot needs to know which configuration is **applied, registers bean definitions, and has its conditions evaluated** before another configuration. Use `@AutoConfiguration(before = ..., after = ...)`, `beforeName`/`afterName`, `@AutoConfigureBefore`/`@AutoConfigureAfter`; in some cases, use `@AutoConfigureOrder`.
2. **Priority order within a list or extension point**: Spring needs to know which bean/callback should appear first when **sorting candidates**. Use `@Order` or the `Ordered` interface, depending on the API consuming the beans.
3. **Bean initialization/destruction order with dependencies**: Spring needs to ensure bean A exists and finishes initializing before creating bean B. Use dependency injection (preferred when B actually needs A) or `@DependsOn("beanName")` for intentional initialization dependencies.

These three orderings are **not equivalent** and cannot substitute for one another by raising or lowering an `order` number.

### Decision table

| What to control | Appropriate tool | Direct effect | Does not guarantee |
| --- | --- | --- | --- |
| Auto-configuration A applied before/after B | `@AutoConfiguration(before/after)`; `@AutoConfigureBefore`/`@AutoConfigureAfter` | Configuration processing order, registering **bean definitions**, and evaluating related conditions | Bean **instance** creation order or business execution |
| Relative priority among unrelated auto-configs | `@AutoConfigureOrder` | Auto-configuration application order | Bean lifecycle |
| `List<Handler>` sorted by priority | `@Order` on class/`@Bean`, or `Ordered#getOrder()` | Candidate position in a collection/extension point that supports ordering | Singleton initialization order |
| `ApplicationRunner`/`CommandLineRunner` running in order | `@Order` or `Ordered` on the runner | **Runner callback invocation** order when Boot executes runners | Beans being initialized in that exact order |
| Bean B initializes only after bean A | Constructor/`@Bean` parameter dependency, or `@DependsOn("a")` | Initialization relationship A before B; for singletons, also affects destruction order | Auto-configuration processing order or bean position in a `List` |

**Key question:** are you talking about **bean definition registration**, **sorting objects**, or **bean instance initialization**?

## 2. Auto-configuration ordering: priority at bean *definition* time

### 2.1. `@AutoConfiguration(after = ...)` and `before = ...`

Suppose a library has two auto-configurations:

- `CoreAutoConfiguration` registers bean `CorePort`.
- `FeatureAutoConfiguration` registers `OptionalAdapter` only when a `CorePort` bean already exists.

```java
@AutoConfiguration
public class CoreAutoConfiguration {

    @Bean
    public CorePort corePort() {
        return new CorePort("core");
    }
}
```

```java
@AutoConfiguration(after = CoreAutoConfiguration.class)
public class FeatureAutoConfiguration {

    @Bean
    @ConditionalOnBean(CorePort.class)
    public OptionalAdapter optionalAdapter(CorePort corePort) {
        return new OptionalAdapter("connected:" + corePort.id());
    }
}
```

The two snippets illustrate the structure, assuming `CorePort` and `OptionalAdapter` are already defined. The `after` attribute states that **when auto-configuration candidates are processed by Spring Boot**, `CoreAutoConfiguration` should be applied before `FeatureAutoConfiguration`. Consequently, when `@ConditionalOnBean(CorePort.class)` is evaluated, the bean definition for `CorePort` has already had the chance to be registered.

Three points to understand:

- `after` is a **configuration application order relationship**; it does not mean `corePort()` is always **called to create an instance** before every bean of `FeatureAutoConfiguration`.
- `@ConditionalOnBean` and `@ConditionalOnMissingBean` are especially sensitive to **which bean definitions have been processed up to the check point**. Thus auto-configuration order can determine whether a condition matches.
- `after` **does not create a dependency by itself**. If B actually needs object A during initialization, declare A as a constructor/`@Bean` parameter of B, like `optionalAdapter(CorePort corePort)` above.

An equivalent alternative in intent:

```java
@AutoConfiguration
@AutoConfigureAfter(CoreAutoConfiguration.class)
public class FeatureAutoConfiguration {
    // ...
}
```

To place configuration A before B, you can write `@AutoConfiguration(before = FeatureAutoConfiguration.class)` on A. When referencing by class name to avoid compile-time coupling, use `beforeName`/`afterName`:

```java
@AutoConfiguration(
    afterName = "com.example.vendor.VendorAutoConfiguration"
)
public class CustomAutoConfiguration {
    // ...
}
```

This is an **API example**, not a standalone program: replace the class name according to the actual library. Use the `Name` variants when you do not want to import an optional auto-configuration class directly.

### 2.2. How does `@AutoConfigureOrder` differ from `@Order`?

Spring Boot also has `@AutoConfigureOrder` for auto-configurations needing relative priority without an **explicit before/after relationship to a specific class**:

```java
@AutoConfiguration
@AutoConfigureOrder(-100)
public class EarlyInfrastructureAutoConfiguration {
    // ...
}
```

Smaller numbers mean higher priority. However, `@AutoConfigureOrder` only controls **the order of auto-configuration candidates**, and does not guarantee singleton creation order.

`@Order` is Spring Framework's general annotation. It can influence the processing order of some regular `@Configuration` classes, yet it is **not the standard tool for expressing dependencies between two Spring Boot auto-configurations**. In a starter, prefer:

- Clear A before/after B relationship → `@AutoConfiguration(before/after)`.
- Need auto-configuration priority without a specific class reference → `@AutoConfigureOrder`.
- Want to sort multiple beans of the same interface when consumed → `@Order`/`Ordered` on **the relevant beans**, rather than putting `@Order` on an auto-configuration expecting its internal `@Bean` methods to be sorted accordingly.

### 2.3. Order in `AutoConfiguration.imports` is not a lifecycle contract

A Spring Boot 3.x starter declares auto-configurations via:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Each line specifies a fully qualified class name. Spring Boot collects, filters, and sorts candidates based on auto-configuration metadata, including `before`/`after` relationships. **Do not rely on swapping two lines in imports to dictate which bean initializes first**.

Auto-configuration order also does not dictate when a `@Bean` method is invoked: Spring can create beans according to the dependency graph and lifecycle rules. This is an important design boundary in Spring Boot.

## 3. `@Order`: priority when *sorting* beans/callbacks

### 3.1. Annotation declaring an order number

`@Order` lives in `org.springframework.core.annotation.Order`:

```java
public interface Handler {
    String name();
}

@Order(10)
public class AuditHandler implements Handler {
    @Override
    public String name() {
        return "audit";
    }
}

@Order(30)
public class ReportHandler implements Handler {
    @Override
    public String name() {
        return "report";
    }
}
```

This is an illustrative snippet with independent types, not a complete application. When `Handler` beans are sorted by Spring for a `List<Handler>`, `AuditHandler` normally precedes `ReportHandler` because `10 < 30`.

You can place the annotation directly on a `@Bean` method if you do not own the class or want to order each bean definition individually:

```java
@Bean
@Order(10)
Handler auditHandler() {
    return () -> "audit";
}

@Bean
@Order(30)
Handler reportHandler() {
    return () -> "report";
}
```

The two methods are assumed to reside in a `@Configuration` class with the `Handler` interface above. With collection injection or `ObjectProvider.orderedStream()`, Spring reads candidates' order metadata.

**Note:** `@Order(10)` does not mean the bean is guaranteed to be created 10th or initialized before `@Order(30)`. It states **priority in a sorting operation that honors order**. A collection created manually via `new ArrayList<>()` will not sort itself just because its elements carry annotations.

### 3.2. `Ordered`: objects supplying their own order

`Ordered` lives in `org.springframework.core.Ordered`. Instead of a static number on an annotation, the object returns a number via `getOrder()`:

```java
public final class DynamicHandler implements Handler, Ordered {

    private final int priority;

    public DynamicHandler(int priority) {
        this.priority = priority;
    }

    @Override
    public String name() {
        return "dynamic";
    }

    @Override
    public int getOrder() {
        return priority;
    }
}
```

This snippet requires importing `Ordered` and the `Handler` interface declared earlier. A `new DynamicHandler(-10)` bean takes precedence over an `@Order(10)` bean in a compatible sort.

Both `@Order` and `Ordered` follow the **smaller number = higher priority** convention; `Ordered.HIGHEST_PRECEDENCE`/`Ordered.LOWEST_PRECEDENCE` can be used when extremes are needed. `Ordered` is useful when the value is computed at runtime or when a class implements a Spring API with an ordering contract. `@Order` is usually sufficient for fixed values.

Distinguish the `PriorityOrdered` interface: it is a specialization of `Ordered` treated as a separate higher-priority tier by certain Spring sorting algorithms. Do not assume every extension point treats them identically; check the contract of the bean consumer.

### 3.3. Handler order does not mean initialization order

Suppose Spring has already initialized two beans `audit` and `report`, and then a service injects:

```java
public Pipeline(List<Handler> handlers) {
    this.handlers = handlers;
}
```

At an injection point supporting ordering, Spring sorts beans according to `@Order` or `Ordered`. Meanwhile, the initialization order of `audit`/`report` depends on the **dependency graph**; `@Order` does not force Spring to create `audit` before `report`.

For `ApplicationRunner` and `CommandLineRunner`, Spring Boot also supports `Ordered`/`@Order` to sort **callback execution order** after the context has started. This remains distinct from when the runner **instances** are created.

## 4. `@DependsOn`: bean *initialization* dependency by name

### 4.1. When is it needed?

`@DependsOn` lives in `org.springframework.context.annotation.DependsOn`. It requires the annotated bean to **wait for the named beans to initialize first**:

```java
@Configuration(proxyBeanMethods = false)
public class WorkerConfiguration {

    @Bean("worker")
    @DependsOn("initializer")
    public Worker worker() {
        return new Worker();
    }

    @Bean("initializer")
    public Initializer initializer() {
        return new Initializer();
    }
}
```

This is an illustrative snippet; `Worker`/`Initializer` are not defined here. Even though `worker()` appears before `initializer()` in source code, `@DependsOn("initializer")` forces Spring to create/initialize the bean named `initializer` before initializing `worker`.

The annotation takes **bean names**, not class names or package names. If a bean is declared `@Bean("initializer")`, the value in `@DependsOn("initializer")` must match. Multiple dependencies can be listed: `@DependsOn({"cache", "schemaInitializer"})`.

### 4.2. When to use constructor injection instead of `@DependsOn`?

If `Worker` actually needs the `Initializer` object to do its work, declaring the dependency directly is clearer and safer:

```java
@Bean
public Worker worker(Initializer initializer) {
    return new Worker(initializer);
}
```

This forces Spring to resolve `Initializer` before calling the factory method to create `Worker`, while passing the real dependency with compile-time type checking.

`@DependsOn` is useful when there is an **initialization dependency without passing an object**, such as one bean requiring another bean to have performed an auxiliary setup step. Avoid turning it into a long-running workflow coordinator: time-consuming tasks, migrations, retryable jobs, or external system interactions generally need dedicated lifecycle/orchestration mechanisms.

### 4.3. Lifecycle impact and limitations

- For singleton beans, `@DependsOn` also causes specified singleton dependencies to be destroyed **after** the dependent bean, preserving lifecycle teardown order.
- For prototypes or beans created through other paths, do not assume a **global destruction schedule** identical to singletons.
- `@DependsOn` does not govern **auto-configuration registration order**, does not make `@ConditionalOnBean` match if the bean definition is absent, and does not sort `List<Handler>`.
- If circular dependencies are declared—A depends on B, B depends on A—the application may fail to start. Redesign the relationship instead of creating a cycle.
- `@DependsOn` does not automatically "wait for external systems to be ready." An initialized bean does not guarantee a database, message broker, or remote service is operationally ready.

## 5. Spring Boot 3.3.5 / Java 17+ program illustrating all three ordering layers

The example below demonstrates in **a single run** three distinct phenomena:

1. `FeatureAutoConfiguration` is ordered **after** `CoreAutoConfiguration` so `@ConditionalOnBean(CorePort.class)` sees the matching bean definition.
2. `Handler` beans are sorted by `Ordered` and `@Order` when calling `orderedStream()`.
3. `@DependsOn("setup")` forces bean `setup` to initialize before `job`, even though the `job` method is written earlier in code.

### 5.1. File structure

```text
order-layers-demo/
├── pom.xml
└── src/main/
    ├── java/
    │   └── demo/
    │       ├── api/
    │       │   ├── CorePort.java
    │       │   └── OptionalAdapter.java
    │       ├── app/
    │       │   └── DemoApplication.java
    │       └── autoconfigure/
    │           ├── CoreAutoConfiguration.java
    │           └── FeatureAutoConfiguration.java
    └── resources/
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
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
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>order-layers-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
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

### 5.3. `src/main/java/demo/api/CorePort.java`

```java
package demo.api;

public record CorePort(String id) {
}
```

### 5.4. `src/main/java/demo/api/OptionalAdapter.java`

```java
package demo.api;

public record OptionalAdapter(String source) {
}
```

### 5.5. `src/main/java/demo/autoconfigure/CoreAutoConfiguration.java`

```java
package demo.autoconfigure;

import demo.api.CorePort;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class CoreAutoConfiguration {

    @Bean
    public CorePort corePort() {
        return new CorePort("core");
    }
}
```

### 5.6. `src/main/java/demo/autoconfigure/FeatureAutoConfiguration.java`

```java
package demo.autoconfigure;

import demo.api.CorePort;
import demo.api.OptionalAdapter;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = CoreAutoConfiguration.class)
public class FeatureAutoConfiguration {

    @Bean
    @ConditionalOnBean(CorePort.class)
    public OptionalAdapter optionalAdapter(CorePort corePort) {
        return new OptionalAdapter("connected:" + corePort.id());
    }
}
```

There are **two distinct relationships** here:

- `after = CoreAutoConfiguration.class` ensures the configuration providing `corePort` is processed first, so `optionalAdapter`'s `@ConditionalOnBean` condition sees the existing **bean definition**.
- The `CorePort corePort` parameter on the `@Bean` method creates an **actual instance dependency**: Spring must resolve a `CorePort` before invoking the `optionalAdapter()` factory method.

If you removed the parameter while keeping `after`, auto-configuration processing order would still apply, yet there would be no corresponding **dependency injection edge** during instance creation.

### 5.7. `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

```text
demo.autoconfigure.FeatureAutoConfiguration
demo.autoconfigure.CoreAutoConfiguration
```

Intentionally list `FeatureAutoConfiguration` **before** `CoreAutoConfiguration` in the file to demonstrate that `@AutoConfiguration(after = ...)` is **candidate** sorting metadata. The two classes are loaded via imports rather than component scanning, following proper auto-configuration organization in Spring Boot 3.x.

### 5.8. `src/main/java/demo/app/DemoApplication.java`

```java
package demo.app;

import demo.api.OptionalAdapter;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.stream.Collectors;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.DependsOn;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;

@SpringBootApplication
public class DemoApplication {

    private static final List<String> INIT_EVENTS =
            new CopyOnWriteArrayList<>();

    public interface Handler {
        String name();
    }

    public record WeightedHandler(String name, int priority)
            implements Handler, Ordered {

        @Override
        public int getOrder() {
            return priority;
        }
    }

    @Bean
    @Order(30)
    public Handler lastHandler() {
        return () -> "last";
    }

    @Bean
    @Order(10)
    public Handler firstHandler() {
        return () -> "first";
    }

    @Bean
    public Handler dynamicHandler() {
        return new WeightedHandler("dynamic", -10);
    }

    @Bean("job")
    @DependsOn("setup")
    public String job() {
        INIT_EVENTS.add("job");
        return "job";
    }

    @Bean("setup")
    public String setup() {
        INIT_EVENTS.add("setup");
        return "setup";
    }

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(DemoApplication.class, args)) {

            OptionalAdapter adapter =
                    context.getBean(OptionalAdapter.class);

            String handlerOrder =
                    context.getBeanProvider(Handler.class)
                            .orderedStream()
                            .map(Handler::name)
                            .collect(Collectors.joining(" > "));

            System.out.println("adapter=" + adapter.source());
            System.out.println("handlers=" + handlerOrder);
            System.out.println("init="
                    + String.join(" > ", INIT_EVENTS));
        }
    }
}
```

**Notable details in the code:**

- `@Order(30)`/`@Order(10)` are placed **on individual `@Bean` methods**, because we are sorting individual `Handler` beans rather than controlling auto-configuration order.
- `WeightedHandler` implements `Ordered` and returns `-10` at runtime. `orderedStream()` sorts **-10, 10, 30**.
- The `job()` method is written **before** `setup()`. `@DependsOn("setup")` guarantees `setup` finishes initializing before `job`. `INIT_EVENTS` records only these two beans to keep output clear.
- The `demo.autoconfigure` classes reside in a sibling package of `demo.app`, outside `DemoApplication`'s default component-scan package. Boot picks them up through `AutoConfiguration.imports`.

### 5.9. Running the program

Requires **JDK 17+**, **Maven 3.6+**, and ability to download Maven dependencies on first build. From the `order-layers-demo` directory:

```bash
mvn -q -DskipTests package
java -jar target/order-layers-demo-0.0.1-SNAPSHOT.jar --spring.main.banner-mode=off --logging.level.root=OFF
```

**Lines printed by the program itself:**

```text
adapter=connected:core
handlers=dynamic > first > last
init=setup > job
```

Line-by-line explanation of the output:

1. `adapter=connected:core`: `CorePort` was registered as a bean definition before `FeatureAutoConfiguration`'s condition was evaluated; the adapter also received the `CorePort` instance via dependency injection.
2. `handlers=dynamic > first > last`: when calling `ObjectProvider.orderedStream()`, `dynamic` has `getOrder() = -10`, followed by `first` with `@Order(10)`, and finally `last` with `@Order(30)`.
3. `init=setup > job`: `@DependsOn("setup")` forced `setup` to initialize before `job`. This line **does not stem** from `@Order` numbers.

The example does not claim a fixed initialization order for **all** singletons in Spring Boot. Only the `setup -> job` relationship is constrained at bean initialization level; unrelated beans may be created at different times.

## 6. Easy-to-confuse cases

### 6.1. "Putting `@Order(1)` on an auto-configuration so conditions see its beans first"

This does not express Spring Boot's auto-configuration ordering contract. Use `@AutoConfiguration(before = .../after = ...)` or `@AutoConfigureBefore`/`@AutoConfigureAfter`, and place `@ConditionalOnBean` in the appropriate auto-configuration.

If you want relative priority among auto-configurations without naming class relationships explicitly, use `@AutoConfigureOrder`. Do not assume `@Order(1)` on a `@Configuration` class causes all its `@Bean`s to be created first.

### 6.2. "`@AutoConfiguration(after = A.class)` guarantees bean A is initialized before bean B"

No. It guarantees **configuration A is applied before configuration B** during auto-configuration sorting. If B needs A at runtime, declare:

```java
@Bean
public B b(A a) {
    return new B(a);
}
```

This snippet is illustrative and assumes types `A`/`B` exist. Spring creates/resolves bean A before calling `b(a)`. If only an initialization dependency without passing the object is needed, consider `@DependsOn("a")`.

### 6.3. "`@DependsOn` can fix an unmatched `@ConditionalOnBean`"

No. `@ConditionalOnBean` inspects **already-processed bean definitions** when the condition is evaluated. `@DependsOn` affects **instance initialization**, which occurs in a different phase. If an auto-configuration depends on another auto-configuration's bean definition, handle order with `after`/`before`.

### 6.4. "`@Order` always forces all callbacks or components to run first"

There is no universal global scheduler for every `@Order` annotation. It only applies in **mechanisms that actually sort by order**, such as injecting a matching bean collection, ordering `ApplicationRunner`/`CommandLineRunner`, or specific extension points. For specialized APIs like servlet filters, interceptors, event listeners, advice, security chains, etc., check **that API's ordering contract** rather than guessing from the annotation alone.

### 6.5. "Larger `@Order` numbers run earlier"

The opposite: in Spring's `Ordered` convention, **smaller numbers have higher priority**. For example, `-10` takes precedence before `10`, then `30`. Do not rely on order if multiple beans share the same order value and strict order is required; declare distinct values or genuine dependency relationships.

### 6.6. "`@Order` and `@Primary` are the same thing"

No. `@Primary` selects a preferred candidate when multiple candidates exist **for a single injection point**; `@Order` and `Ordered` sort candidates in **collections or pipelines supporting sorting**. `@Primary` is not a substitute for an ordered handler chain.

### 6.7. "Reordering `@Bean` methods in source code is enough"

Do not rely on method declaration order to guarantee an initialization relationship. If bean B truly depends on A, express the graph via constructor injection, `@Bean` parameters, or `@DependsOn`. This remains stable across refactorings such as moving methods, splitting `@Configuration` classes, or adding new beans.

### 6.8. "`@DependsOn` causes two beans to start running jobs in order"

This annotation guarantees **bean initialization**, does not automatically invoke business methods, and does not replace scheduling. If both beans are runners, use the runner ordering contract for callback order, and design explicit dependencies/lifecycle if initialization relationships also exist.

## 7. Practical testing and diagnostic approach

**Step 1 — identify which kind of order is failing.** Ask: is a missing bean definition causing `@ConditionalOnBean` to fail, is a handler list sorted wrongly, or is a bean initializing too early? Each requires a different tool.

**Step 2 — inspect the Condition Evaluation Report.** Run Spring Boot with `--debug` to see which conditions matched or did not match. If `FeatureAutoConfiguration` does not create a bean, verify the candidate is loaded via `AutoConfiguration.imports`, the dependency bean definition exists, and `before`/`after` metadata is right. Logs may vary by Boot version.

**Step 3 — inspect the sorted collection.** For a Spring-injected `List<Handler>` or `ObjectProvider.orderedStream()`, print each bean's actual name and order. If you pull from a `Map` or build a list manually without Spring sorting it, do not expect annotations to sort that collection automatically. Verify whether `@Bean` methods already carry their own `@Order`.

**Step 4 — observe lifecycle in the right place.** Add logs in constructors/`@PostConstruct` or factory methods to observe bean creation timing; avoid using the order bean names appear in a debugger as proof. If you hit "A isn't ready when B is created," add a real dependency or `@DependsOn` with the right bean name. If A is an external system, check readiness separately.

**Step 5 — write tests for each behavioral layer.**

- For auto-configurations, use `ApplicationContextRunner` with `AutoConfigurations.of(...)` to verify bean presence/absence after conditions; also test when users supply replacement beans. This observes **bean registration results**, rather than inferring from startup logs.
- For `@Order`/`Ordered`, assert that the Spring-injected list or `orderedStream()` produces the expected order.
- For `@DependsOn`, record initialization events inside the beans and assert `setup` appears before `job`.
- If auto-configuration ordering affects conditions, test inside a context that actually runs auto-configuration sorting; do not merely `new` the two classes or import them in a way that bypasses Spring Boot's path.

## 8. Quick rules to remember and exercises

You can remember them with three verbs:

- **Apply** auto-configurations: `@AutoConfiguration(before/after)` / `@AutoConfigureOrder`.
- **Sort** components: `@Order` / `Ordered`.
- **Initialize** dependent beans: injection / `@DependsOn`.

**Exercise 1.** Auto-config B has `@ConditionalOnBean(CacheManager.class)`, while auto-config A provides `CacheManager`. What should you choose? **`@AutoConfiguration(after = A.class)` on B**, while expressing runtime dependency via injection if B's bean needs object A.

**Exercise 2.** Three handlers process a chain in the order Audit → Security → Response. What should you choose? **`@Order` or `Ordered`** on the handlers, and confirm the consumer actually honors ordering.

**Exercise 3.** Bean `reportWriter` needs bean `fileSystemInitializer` to finish initializing first without calling its API. What should you choose? **`@DependsOn("fileSystemInitializer")`** (or design a clearer dependency if an actual object relationship exists).

**Exercise 4.** A `CommandLineRunner` has `@Order(1)`. Does that guarantee that runner's singleton initializes before a singleton with `@Order(2)`? **No.** The order value affects **runner callback invocation order**; singleton initialization is determined by the bean dependency graph.

**Exercise 5.** A starter has filter, service, and repository beans. To give the filter high priority when a web stack orders filters, should you use `@AutoConfiguration(before = ...)` to force the filter callback to run first? **No.** You must control order via **the corresponding filter ordering/registration mechanism**; auto-configuration application order is not filter execution order.

## Official documentation

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): `@AutoConfiguration(before/after)`, `@AutoConfigureOrder`, `AutoConfiguration.imports`, and distinguishing bean definition order from initialization order.
- [Spring Boot 3.3 — `@AutoConfiguration` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): `before`, `after`, `beforeName`, `afterName` attributes.
- [Spring Framework — Using `@Autowired`, Ordering of collection injection](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html): `@Order`/`Ordered` for collection injection and notes distinguishing it from singleton startup order.
- [Spring Framework 6.1 — `Ordered` API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/Ordered.html): convention that smaller order numbers have higher priority.
- [Spring Framework — `@DependsOn` API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/DependsOn.html): bean initialization and destruction dependency relationships.
