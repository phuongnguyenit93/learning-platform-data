# The @PostConstruct Callback After Dependency Injection Completes in Spring Framework

## 1. What Problem Does @PostConstruct Solve?

In the Spring IoC Container, Spring typically creates a bean via a constructor or factory method, supplies its declared dependencies and properties, and only then runs initialization callbacks. The `@PostConstruct` annotation marks a method that Spring should invoke **after normal dependency injection and property population for the bean have completed**, before the bean is considered to have finished its standard initialization phase.

```java
import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Component;

@Component
public class ExampleService {
    @PostConstruct
    public void initialize() {
        // Prepare required state after dependencies have been injected.
    }
}
```

The snippet above is a Spring component; for the callback to run, the bean must be created by a container with the corresponding annotation processor registered. Calling `new ExampleService()` directly will **not** cause Spring to automatically invoke `initialize()`.

This is a lifecycle hook **each time a target bean is created and initialized by Spring**, not a hook per HTTP request, per method call, or when the entire system has successfully started. For a typical eager singleton, the callback is invoked once per `ApplicationContext` for that bean definition. For a prototype or scoped target, the callback is tied to **each time a target is created**; for a lazy singleton, the callback usually waits until the bean is actually initialized.

### When to use it?

Tasks well suited for `@PostConstruct` include:

- Validating configuration constraints after injecting `@Value` or dependencies via setters.
- Preparing an immutable lookup table, converter, parser, or data structure reused across the bean.
- Computing a value that depends on both constructor arguments and properties assigned by Spring after construction.
- Registering small internal resources and establishing a controlled "ready" state before the bean is used normally.
- Detecting configuration errors early with a clear exception during bean initialization.

Avoid using this hook for long network calls, indefinite blocking, spawning background threads yourself, sending business events, or executing actions with hard-to-rollback side effects. Such tasks may require a startup mechanism after context refresh (`ApplicationRunner`/`CommandLineRunner` in Spring Boot, `ContextRefreshedEvent`, or `SmartLifecycle` depending on the problem) and a dedicated shutdown mechanism.

## 2. Where Does @PostConstruct Sit in the Bean Lifecycle?

A typical path for a Spring-managed bean without unusual reference cycles:

```text
1. Spring locates the bean definition and chooses a constructor / factory method
                          |
                          v
2. Instance creation: constructor runs
                          |
                          v
3. Property population and dependency injection:
   @Autowired fields, @Autowired setters, @Value, @Resource...
                          |
                          v
4. Relevant Aware callbacks (BeanNameAware, BeanFactoryAware...)
   and BeanPostProcessors running before initialization
                          |
                          v
5. @PostConstruct                <-- this lesson's hook
                          |
                          v
6. InitializingBean.afterPropertiesSet()
                          |
                          v
7. Custom init method (e.g., @Bean(initMethod = "init"))
                          |
                          v
8. BeanPostProcessors after initialization
   (may create/wrap an AOP proxy)
                          |
                          v
9. Bean is supplied to consumers and operates
                          |
                          v
10. When scope/container is destroyed: appropriate destroy callbacks
```

This is a learning diagram for the normal bean creation flow. More precisely, `CommonAnnotationBeanPostProcessor` processes `@PostConstruct` during the `postProcessBeforeInitialization` phase. There can be multiple `BeanPostProcessor` instances running before/after initialization; the order among processors depends on configuration and ordering rules. Therefore, the diagram does not guarantee that all processors run before `@PostConstruct`, and Spring can have complex cases such as early references/proxies and circular dependencies.

What Spring guarantees is that the initialization callback runs once dependencies have been **supplied** to the bean according to its bean definition. It does **not** mean:
- Every singleton in the context has finished initializing.
- Every lazy dependency/proxy has resolved its inner target.
- The HTTP application is ready to receive traffic.
- All external database/messaging services are up and running.
- No asynchronous work is still in progress.
- A bean managed by another container is also ready.

Most normal direct dependency relationships are resolved before the callback on the consumer bean runs. If you need ordering between beans that have no injection relationship, declare the relationship explicitly via a dependency or `@DependsOn` as needed; `@Order` is not a universal tool for controlling startup order.

## 3. Distinguishing Constructor Injection, Field/Setter Injection, and @PostConstruct

### Constructor injection

```java
@Component
class InvoiceService {
    private final TaxPolicy taxPolicy;

    InvoiceService(TaxPolicy taxPolicy) {
        this.taxPolicy = taxPolicy;
        // taxPolicy is already available in the constructor.
    }
}
```

`TaxPolicy` is an application interface/bean that must be defined separately; the snippet is illustrative and requires importing `Component`. If all required data is in the constructor and the object can be fully initialized right then, **the constructor is the preferred choice**: required dependencies are explicit and fields can be `final`.

### Setter or field injection

```java
@Component
class InvoiceService {
    @Autowired
    private TaxPolicy taxPolicy;

    InvoiceService() {
        // Here taxPolicy has not yet been assigned by @Autowired.
    }

    @PostConstruct
    void init() {
        // taxPolicy has been injected on the normal initialization path.
    }
}
```

Requires importing `Component`, `Autowired`, `PostConstruct`, and defining `TaxPolicy`. With field injection, the constructor runs **before** Spring assigns the field. With an `@Autowired` setter, the setter is called during the population phase. Therefore, you should not access field-injected dependencies inside the constructor. After normal injection finishes, `@PostConstruct` can use them to prepare derived data.

Do not treat "injected" as "always non-null" if you declared the injection as optional, `@Autowired(required = false)`, `Optional<T>`, `@Nullable`, or an optional property. The callback still needs to validate real constraints.

### @Value and configuration

```java
@Component
class RuntimeSettings {
    @Value("${features.max-items:100}")
    private int maxItems;

    @PostConstruct
    void validate() {
        if (maxItems <= 0) {
            throw new IllegalStateException(
                    "features.max-items must be positive");
        }
    }
}
```

In a Spring context with appropriate `@Value` property resolution, the callback checks the value **after binding/injection**. However, in Spring Boot, if multiple configuration properties are related, `@ConfigurationProperties` combined with validation is usually better suited for strongly typed configuration. The example above is an illustrative fragment, not a standalone Java executable.

## 4. The Right API in Java 17+ and Modern Spring Framework

Use `jakarta.annotation.PostConstruct` in Spring Framework 6.x/7.x (migrated from the legacy Java EE/Jakarta namespace). Do **not** mistakenly import `javax.annotation.PostConstruct` when building on Spring 6+/Boot 3+.

```java
import jakarta.annotation.PostConstruct;
```

Java SE 17 does not bundle the Jakarta Annotations API. With Maven/Spring Framework, you need a dependency containing `jakarta.annotation`; Spring Boot starters usually provide it through the dependency graph, while a minimal Spring Core application should declare it explicitly if needed.

Rules for the method:
- An instance method, taking no parameters, with return type `void`.
- Must not be a static method.
- Should have a meaningful business name, such as `validateConfiguration` or `buildIndex`.
- Should avoid checked exceptions; if you need to report an initialization error, throw `IllegalStateException` or a meaningful unchecked exception.
- May be private/package-private/public depending on runtime access conditions; using a simple method that does not rely on proxies is safe when dealing with Java module access.
- Does not return an object or reassign a field reference; Spring merely invokes the method and ignores any return value.
- With multiple `@PostConstruct` methods, ordering across class hierarchies/annotation-processing scopes can be subtle; consolidate order-dependent steps into one clear callback.
- Avoid duplicating the same logic across other lifecycle hooks unnecessarily.

Under the Jakarta `PostConstruct` contract, the method performs initialization after injection and runs only once per initialized target instance within its managed lifecycle. Spring can support different method visibilities, though with JPMS you must mind package/module access.

### Conditions for Spring to recognize the annotation

In applications configured with `AnnotationConfigApplicationContext` or Spring Boot, `CommonAnnotationBeanPostProcessor` is usually registered automatically. This mechanism handles `@PostConstruct`, `@PreDestroy`, and `@Resource`. With a low-level `BeanFactory` or minimal XML configuration, you must register the appropriate annotation processors or `<context:annotation-config/>`; otherwise Spring may create the bean while ignoring the annotation.

An object created by application code with `new`, deserialized, or created by another framework without going through the Spring bean lifecycle will **not automatically run** Spring callbacks. If you need to wire an already-created object, you must proactively use the appropriate API/container and understand that object's lifecycle/ownership.

## 5. Complete Spring Core Example: Observing Constructor → Injection → @PostConstruct

This example uses **Java 17+, Maven 3.9+, and Spring Framework 6.2.12** and requires only the Core Container, with no web server. All sources are listed and no DB is used. We create a `Catalog` via constructor injection, receive an additional `Formatter` via an `@Autowired` setter, and then build a processed snapshot inside `@PostConstruct`. The program also illustrates the ordering of `InitializingBean`, `@Bean(initMethod=...)`, and destruction callbacks.

Project structure:

```text
postconstruct-demo/
├── pom.xml
└── src/main/java/edu/example/lifecycle/
    ├── Main.java
    ├── AppConfig.java
    ├── SourceData.java
    ├── Formatter.java
    └── Catalog.java
```

**pom.xml**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>postconstruct-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>jakarta.annotation</groupId>
            <artifactId>jakarta.annotation-api</artifactId>
            <version>2.1.1</version>
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
                    <mainClass>edu.example.lifecycle.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**src/main/java/edu/example/lifecycle/SourceData.java**

```java
package edu.example.lifecycle;

public record SourceData(String text) {
}
```

**src/main/java/edu/example/lifecycle/Formatter.java**

```java
package edu.example.lifecycle;

public class Formatter {
    public String format(String input) {
        return input.toUpperCase(java.util.Locale.ROOT);
    }
}
```

**src/main/java/edu/example/lifecycle/Catalog.java**

```java
package edu.example.lifecycle;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.beans.factory.annotation.Autowired;

public class Catalog implements InitializingBean, DisposableBean {
    private final SourceData source;
    private Formatter formatter;
    private String preparedValue;

    public Catalog(SourceData source) {
        this.source = source;
        System.out.println("1. constructor: " + source.text());
    }

    @Autowired
    public void setFormatter(Formatter formatter) {
        this.formatter = formatter;
        System.out.println("2. @Autowired setter");
    }

    @PostConstruct
    public void prepare() {
        // Both constructor and setter dependencies are available.
        preparedValue = formatter.format(source.text());
        System.out.println("3. @PostConstruct: " + preparedValue);
    }

    @Override
    public void afterPropertiesSet() {
        System.out.println("4. afterPropertiesSet()");
    }

    public void customInit() {
        System.out.println("5. custom init()");
    }

    public String value() {
        return preparedValue;
    }

    @PreDestroy
    public void beforeDestroy() {
        System.out.println("7. @PreDestroy");
    }

    @Override
    public void destroy() {
        System.out.println("8. DisposableBean.destroy()");
    }

    public void customDestroy() {
        System.out.println("9. custom destroy()");
    }
}
```

**src/main/java/edu/example/lifecycle/AppConfig.java**

```java
package edu.example.lifecycle;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AppConfig {
    @Bean
    public SourceData sourceData() {
        return new SourceData("spring");
    }

    @Bean
    public Formatter formatter() {
        return new Formatter();
    }

    @Bean(initMethod = "customInit", destroyMethod = "customDestroy")
    public Catalog catalog(SourceData sourceData) {
        return new Catalog(sourceData);
    }
}
```

**src/main/java/edu/example/lifecycle/Main.java**

```java
package edu.example.lifecycle;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            Catalog catalog = context.getBean(Catalog.class);
            System.out.println("6. value(): " + catalog.value());
        }
        // try-with-resources closes the context, invoking destroy callbacks
    }
}
```

In the `postconstruct-demo` directory, run:

```bash
mvn -q compile exec:java
```

**Stdout lines printed by the application:**

```text
1. constructor: spring
2. @Autowired setter
3. @PostConstruct: SPRING
4. afterPropertiesSet()
5. custom init()
6. value(): SPRING
7. @PreDestroy
8. DisposableBean.destroy()
9. custom destroy()
```

Spring/Maven may produce additional environment-dependent logs, but the `System.out.println` lines above have a deterministic order in a single-bean example without cycles or custom proxies. `AnnotationConfigApplicationContext(AppConfig.class)` refreshes the context right inside its constructor, causing the `catalog` singleton to be initialized **before** `context.getBean(...)` in `Main`. Consequently, steps 1–5 appear before 6. `try-with-resources` closes the context at the end of the block, so destruction callbacks 7–9 run next.

The key takeaway of the example: the constructor only receives `SourceData`; `Formatter` is injected afterward via an `@Autowired` setter. Inside `prepare()`, both are ready. If you wrote `formatter.format(...)` in `Catalog`'s constructor, `formatter` would still be `null` and fail.

Three different initialization mechanisms applied to the same bean run in the order `@PostConstruct` → `InitializingBean.afterPropertiesSet()` → configured `initMethod`. The three corresponding destruction mechanisms run in the order `@PreDestroy` → `DisposableBean.destroy()` → custom destroy method, if the bean is destroyed through a Spring-managed lifecycle. In real applications, usually only **one** style is chosen per purpose to keep code clean.

## 6. How Spring Executes @PostConstruct Under the Hood

An annotation is only metadata. `CommonAnnotationBeanPostProcessor` (via the `InitDestroyAnnotationBeanPostProcessor` mechanism) is the component that detects and invokes the marked method.

A simplified version of the process:

```text
createBeanInstance()
  └─ resolve constructor/factory dependencies
  └─ construct instance

populateBean()
  └─ AutowiredAnnotationBeanPostProcessor injects @Autowired/@Value...
  └─ other applicable processors/property population

initializeBean()
  └─ invoke Aware callbacks such as BeanNameAware
  └─ apply BeanPostProcessors.beforeInitialization(...)
       └─ CommonAnnotationBeanPostProcessor invokes @PostConstruct
  └─ invoke InitializingBean.afterPropertiesSet()
  └─ invoke configured init methods
  └─ apply BeanPostProcessors.afterInitialization(...)
       └─ may wrap the bean with a proxy
```

The APIs above describe the logic conceptually, not an exact source copy of a specific Spring version. With application-written `BeanPostProcessor` implementations, actual ordering also depends on priority/order; never use this diagram to assume that all other beans have been created or all AOP advice has taken effect.

**Consequence when using AOP:** `@PostConstruct` is typically called on the **raw target bean**, before the target is wrapped in the final AOP proxy. Therefore, self-invoking a method annotated with `@Transactional`, `@Async`, `@Cacheable`, or other advice from `@PostConstruct` is not a reliable way to trigger that advice. Even for public methods, self-invocation on the target bypasses the Spring AOP proxy.

Example to avoid:

```java
@Service
class CacheBootstrap {
    @PostConstruct
    void init() {
        refreshInTransaction(); // Do not expect the @Transactional proxy to intercept.
    }

    @Transactional
    public void refreshInTransaction() {
        // DB interaction...
    }
}
```

This snippet requires importing `@Service`, `@PostConstruct`, `@Transactional`, and transaction configuration; it only illustrates an anti-pattern, not a standalone runnable program. If you need to execute a transaction at startup, move the call to a Spring-managed collaborator bean and choose an appropriate moment once the transaction infrastructure is ready; usually a post-context-refresh initialization hook is better suited for startup tasks.

## 7. @PostConstruct Compared to Other Lifecycle Hooks

| Mechanism | When does it run? | Purpose and caveats |
| --- | --- | --- |
| Constructor / `@Bean` factory | Instance creation | Best suited for establishing immutability and required dependencies via constructor |
| Setter / field `@Autowired`, `@Value` | Injection/population phase | Supplies dependencies/configuration not present in the constructor |
| `@PostConstruct` | After injection, during the before-init phase of BeanPostProcessor | Validates and prepares state after injection |
| `InitializingBean.afterPropertiesSet()` | After `@PostConstruct` | Spring-specific hook for initialization |
| `@Bean(initMethod = "...")` / XML init-method | After `afterPropertiesSet()` when the same bean combines all mechanisms | Hook configured outside the class |
| `BeanPostProcessor.postProcessAfterInitialization` | After init callbacks | Can wrap the bean, e.g. creating an AOP proxy |
| `SmartInitializingSingleton.afterSingletonsInstantiated()` | After pre-instantiation of non-lazy singletons completes | Good for logic needing most eager singletons ready; does not mean all lazy/prototype beans exist |
| `ContextRefreshedEvent` | Context refresh succeeds | ApplicationContext-level hook; may be received multiple times on refresh |
| `ApplicationRunner` / `CommandLineRunner` (Boot) | After Spring Boot context startup per Boot's flow | Runs application-level startup logic; does not replace bean init |
| `SmartLifecycle` | According to container start/stop phases | Manages long-lived components such as listeners/consumers |
| `@PreDestroy` | During the appropriate destruction lifecycle | Cleans up resources before other destroy callbacks |

**Choosing a hook based on what you need to know:**
- Need the bean's own dependencies → constructor or `@PostConstruct`.
- Need most eager singletons created → `SmartInitializingSingleton`.
- Need application-level work after Spring Boot starts the context → runner or corresponding event.
- Need start/stop control of a long-running service → `SmartLifecycle`.
- Need to release resources → `@PreDestroy`/`destroyMethod`, keeping scope limits in mind.

An `ApplicationReadyEvent` in Spring Boot is a Boot event signaling that the application is ready according to its startup flow; this also does **not** prove all external dependencies are healthy. Do not use `@PostConstruct` merely to run a one-time task after the server begins accepting requests, because bean creation may happen before the server is ready.

## 8. Differences Across Singleton, Prototype, and Web Scopes

| Scope | How many times is `@PostConstruct` called? | Destruction callback |
| --- | --- | --- |
| `singleton` | Once when the target bean is created in the container (eager by default) | When the container shuts down cleanly |
| Lazy singleton | Once at the moment the target is first initialized | On context shutdown if the target already exists |
| `prototype` | Each time Spring creates a prototype target and initializes it | Spring does **not** track and destroy each prototype like a singleton; the consumer is responsible for cleanup |
| `request` | Once per request-scoped target used/created | Usually when the request scope ends |
| `session` | Once per HTTP-session-scoped target created | When the session expires/invalidates |
| `application` | Once per target in ServletContext scope | When the application scope/context ends |
| `websocket` (STOMP) | Once per WebSocket-session-scoped target created | When the WebSocket session ends |

A request might not create a request-scoped bean if no code path accesses it. Similarly, an existing WebSocket session does not automatically create every websocket-scoped bean. `@PostConstruct` runs when **the target instance is initialized**, not immediately when the scope is declared.

For a `prototype` bean injected into a singleton via constructor, the prototype target is usually created only once **at the singleton's injection time**. That prototype's `@PostConstruct` does not run every time the singleton calls a method on the dependency. To get a fresh prototype per operation, use `ObjectProvider<T>.getObject()` at the right moment; each new target will go through its own initialization. If using a prototype scoped proxy, target resolution may occur on every intercepted method call; consider any state that needs to span multiple steps.

With request/session scoped proxies, a singleton can hold a proxy reference while the target's `@PostConstruct` typically runs the first time a request/session needs the target. The callback belongs to the target, **not every call through the proxy**. Nor does a proxy automatically propagate the request context to `@Async` threads.

## 9. Handling Exceptions in @PostConstruct

If `@PostConstruct` throws a runtime exception while creating an eager singleton, Spring usually halts bean creation and causes a context initialization failure (for example `BeanCreationException` wrapping the cause). This is a useful **fail-fast** mechanism when required configuration is invalid.

```java
@PostConstruct
void validateAndPrepare() {
    if (endpoint == null || endpoint.isBlank()) {
        throw new IllegalStateException("endpoint must be configured");
    }
    parsedEndpoint = java.net.URI.create(endpoint);
}
```

This example is a fragment of a bean having `endpoint` and `parsedEndpoint` fields; they must be defined/injected in the class. Throwing causes startup to fail if the bean is eagerly instantiated. However, if the bean is lazy or a scoped target not yet created, the error will surface late on first resolution; do not assert that every validation will always happen at application startup.

A few guidelines:
- Exception messages should include the configuration key and remediation, while avoiding leaking tokens/passwords in errors.
- Avoid catching the exception only to log it and let the bean continue in a half-initialized state.
- If opening a file/socket before throwing, consider try/finally or cleanup directly inside the method. Do not rely on `@PreDestroy` to roll back every failed initialization case: the container may not have registered a destroy callback for a bean that failed initialization.
- For external services that may be temporarily unavailable, distinguish **invalid config** (fail fast) from **dependency unavailable** (retry/backoff/readiness). Do not use an infinite busy loop on the initialization thread.

## 10. Thread Safety, State Publication, and Background Tasks

A good use case is building an immutable snapshot before the bean is published:

```java
import java.util.List;
import java.util.Map;
import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Component;

@Component
class RouteIndex {
    private Map<String, Integer> index = Map.of();

    @PostConstruct
    void prepare() {
        List<String> routes = List.of("/users", "/orders");
        index = Map.of(routes.get(0), 1, routes.get(1), 2);
    }

    int priority(String route) {
        return index.getOrDefault(route, 0);
    }
}
```

Normal publication of the bean by the Spring container lets consumers access the initialized bean, and the map is never mutated after construction. In this example, an immutable map is well suited for concurrent reads across many requests. That does **not** mean any mutable `HashMap` written after startup is automatically thread-safe: if runtime updates occur, you need locks, immutable replacement via `volatile`/`AtomicReference`, or concurrent data structures matching your invariants.

### Do not start threads by leaking `this` in callbacks

```java
@PostConstruct
void riskyStart() {
    new Thread(() -> useAllBeanState()).start();
}
```

The fragment above does not compile on its own because `useAllBeanState` is missing. It intentionally illustrates a pattern to handle with caution: the thread is started before remaining init callbacks finish and before the bean is published as its final proxy, so it may observe unexpected state. Managing thread stop/join is also complex, especially if bean initialization fails or the container shuts down.

If you need workers/thread pools:
- Let Spring manage a `TaskExecutor`/`TaskScheduler` or a component with an appropriate lifecycle.
- Prepare lightweight configuration in `@PostConstruct`.
- Actually start work when the application/bean lifecycle permits, with clear shutdown and error-handling mechanisms.
- Never use `Thread.sleep` in init as a trick to "wait for all beans".
- Keep initialization methods fast enough to avoid lengthening application startup time.

## 11. Common Mistakes and How to Fix Them

| Symptom | Common cause | How to resolve |
| --- | --- | --- |
| `@PostConstruct` does not run | Object created with `new`, not managed by Spring; annotation processor not registered | Let Spring create the bean, use `AnnotationConfigApplicationContext`/Boot, or register the processor |
| `javax.annotation.PostConstruct` import fails to compile on Spring 6+ | Using old namespace / missing dependency | Import `jakarta.annotation.PostConstruct` with a compatible Jakarta dependency |
| `@Autowired` field is null in constructor | Constructor runs before field/setter injection | Use constructor injection or defer usage until `@PostConstruct` |
| `@PostConstruct` still sees null | Optional injection, undeclared property, object outside container, unusual cycle handling | Check bean wiring, required/Optional, and container ownership |
| `@Transactional`/`@Async` on method called inside `@PostConstruct` has no effect | Initialization happens before the final AOP proxy; self-invocation | Move logic to a proxied collaborator and trigger at an appropriate lifecycle point |
| Slow/hanging startup | Blocking on network/DB or running long jobs in init | Separate startup workload, use sensible timeouts/retries, use runners/lifecycle |
| Lazy bean only runs callback when first request arrives | Target was not initialized earlier | This is normal; if eager validation is needed, design clear dependencies/triggers |
| Prototype has init callback but cleanup does not run | Container does not automatically manage full destruction of prototypes | Consumer closes resources itself or uses an appropriate scope/lifecycle |
| Testing with Mockito `new` object and expecting hook to run | Unit test does not create a Spring bean | Call setup explicitly in pure unit tests or use an integration test with a context |
| `@PostConstruct` repeats across multiple app instances | Each replica/pod/context has its own lifecycle | Do not use as a global exactly-once job; use distributed coordination |
| Init method called before all other beans are ready | Per-bean hook, not a whole-app ready event | Use context-level lifecycle/runners if needed |
| Runtime state updates after `@PostConstruct` cause races | Finishing init does not make shared mutable fields automatically thread-safe | Use immutable snapshots/locks/atomics matching invariants |

### Step-by-step diagnosis

1. Is the bean actually managed and created by Spring? Check container scan/`@Bean`, lazy singleton, active profile, and conditions.
2. Does the method import `jakarta.annotation.PostConstruct` properly, with a no-arg signature and `void` return type?
3. Is `CommonAnnotationBeanPostProcessor` present in the current context?
4. Have dependencies been supplied, and could any optional/lazy/proxy resolve later?
5. Is there an early exception or circular reference causing bean initialization to fail?
6. Is logic running on the raw target during init when it actually needs advice only active when calls go through a proxy?
7. Is the callback expected to run once per bean instance, per request, or once across the entire cluster? If expectations differ, change the lifecycle design.

## 12. Practical Scenarios and Self-Assessment Questions

**Scenario A — frequently read catalog cache:** A bean injects `ProductRepository` and needs to build an immutable index before the service starts accepting calls. `@PostConstruct` works if the dataset is small, fetching is fast, you want startup to fail on bad configuration, and no transaction/advice via self-call is needed. If loading millions of records from a remote service is required, consider readiness and alternative startup orchestration.

**Scenario B — configuration validation:** A bean receives `@Value("${file.format:csv}")` from Spring and must fail if the value is anything other than `csv`/`json`. `@PostConstruct` is an appropriate place to validate after binding. If configuration parameters involve many fields and structural constraints, look into `@ConfigurationProperties` validation.

**Scenario C — self-starting subscriber:** A bean wants to open a connection, register a listener, and retry on disconnect. `@PostConstruct` can prepare dependencies/config, but starting/stopping a stateful listener usually fits `SmartLifecycle` or a Spring-managed listener container better.

Questions:
1. Why is an `@Autowired` field unavailable in the constructor yet available in `@PostConstruct`?
2. If a bean implements `InitializingBean` and has `@Bean(initMethod="customInit")`, what is the order of the three init callbacks?
3. When does `@PostConstruct` run for a lazy singleton?
4. A prototype bean is requested to be created three times, and each target has `@PostConstruct`: how many times will it run?
5. Why is `@PreDestroy` unreliable for destroying a Spring-created prototype bean?
6. A `@PostConstruct` method calls `this.fetch()` annotated with `@Transactional`: will Spring AOP automatically ensure a transaction?
7. A `@RequestScope` bean has been proxied, but the target has never been resolved: has the target's init callback run yet?
8. Once a bean's `@PostConstruct` finishes, does that mean the HTTP server and all external integrations are ready?
9. Why does calling `new MyComponent()` in a test not automatically invoke `@PostConstruct`?
10. When should you use a constructor instead of an init callback?

**Answers:** (1) Field injection happens after the constructor and before initialization. (2) `@PostConstruct` → `afterPropertiesSet()` → custom init method. (3) When the actual bean is created for the first time, not by default during context refresh. (4) Three times, if all three instances are actually initialized by Spring. (5) The container does not manage automatic destruction for prototypes. (6) No, self-invocation/raw target can bypass the proxy. (7) Not yet; the callback belongs to the target upon creation. (8) Not yet. (9) Because the object does not go through Spring lifecycle processors. (10) When all required dependencies are available to establish invariants at construction time.

## Official Documentation

- Spring Framework — Using @PostConstruct and @PreDestroy: https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/postconstruct-and-predestroy-annotations.html
- Spring Framework — Customizing the Nature of a Bean (lifecycle callbacks, order): https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Framework — Annotation-based Container Configuration: https://docs.spring.io/spring-framework/reference/core/beans/annotation-config.html
- Spring Framework — Using @Autowired: https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html
- Spring Framework — Using the @Bean Annotation: https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html
- Spring Framework — Container Extension Points (BeanPostProcessor): https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html
- Jakarta Annotations specification — @PostConstruct: https://jakarta.ee/specifications/annotations/2.1/apidocs/jakarta.annotation/jakarta/annotation/postconstruct
