# Distinguishing Application-Wide Lazy Initialization from `@Lazy` on a Dependency in Spring Boot

## 1. Core Conclusion

Spring Boot has **at least three distinct places** learners commonly group together as "lazy," yet they do not share the same scope or mechanism:

1. **Application-wide lazy initialization**: configuring `spring.main.lazy-initialization=true` instructs Spring Boot to apply lazy initialization broadly to eligible beans, instead of pre-instantiating most ordinary singletons during startup.
2. **`@Lazy` on a bean definition**: placing `@Lazy` on `@Component`, a `@Bean` method, or a `@Configuration` class to change **when a bean is created**. This mechanism affects the marked bean definitions and does not inherently alter the entire application.
3. **`@Lazy` at a dependency injection point**: placing `@Lazy` on a constructor parameter, `@Autowired` field, or supported injection method. Spring injects a **lazy-resolution proxy** into the receiving object; the proxy defers looking up or initializing the **target** until the target is used through the proxy.

All three can cause some objects to be created later, yet the questions they answer **differ**:

- Global lazy: *Do many beans in the application context need to be initialized right at refresh?*
- Bean-definition `@Lazy`: *Does this specific bean need to be pre-instantiated if nothing has requested it yet?*
- Injection-point `@Lazy`: *When creating bean A, must dependency bean B be resolved and created immediately?*

**Most important takeaway:** `@Lazy` on a dependency **does not turn all beans lazy**; `spring.main.lazy-initialization=true` **does not guarantee all dependencies remain uncreated**; and `@Lazy` on a **bean definition** may fail to defer a bean if another eager singleton requires it directly.

## 2. Foundation: Eager Singletons, Lazy Singletons, and Bean Creation Demand

By default, many `ApplicationContext` implementations in Spring pre-instantiate non-lazy singletons during `refresh()`. This is called **pre-instantiation**: Spring can detect constructor, injection, configuration, or lifecycle callback errors early.

Suppose there are two beans:

```text
OrderController  ----depends-on---->  PricingService
```

With non-lazy singletons on both sides, Spring may create both during the refresh phase. If `OrderController` requires `PricingService` via its constructor, the dependency generally must be resolved so the controller can be constructed.

A singleton bean marked lazy is not forced to pre-instantiate **solely because it exists in the container**. However, when a non-lazy consumer necessarily requires the target to satisfy constructor injection, Spring can **still create the lazy bean at startup** to fulfill the dependency.

```text
Bean A (eager) --constructor requires--> Bean B (@Lazy on definition)

refresh()
  -> create A
      -> A needs B immediately
          -> create B
      -> finish creating A
```

Therefore **`@Lazy` does not mean "never create regardless of who asks."** It mainly changes the **pre-creation policy**; actual demand from a dependency or `getBean` can still trigger target creation.

Conversely, if A's constructor parameter carries `@Lazy`, Spring can supply a proxy instead of forcing immediate retrieval of B:

```text
Bean A (eager) --injection-point @Lazy--> Proxy for B
                                              |
                                              +-- first use --> resolve B
```

These two diagrams explain why **where the annotation is placed** matters just as much as having the annotation.

## 3. Quick Comparison Table

| Aspect | Spring Boot Global Lazy | `@Lazy` on Bean Definition | `@Lazy` at Injection Point |
| --- | --- | --- | --- |
| Usage | `spring.main.lazy-initialization=true` | `@Lazy` on `@Component` / `@Bean` | `@Lazy` on constructor parameter, field, or injection method |
| Scope | Broad across eligible beans in the context | One bean or a configuration group of beans | One **dependency edge** of a consumer |
| Primary effect | Marks many beans to defer pre-instantiation | Defers pre-instantiation of the marked bean | Injects a proxy deferring target resolution |
| Can the consumer bean be eager? | Yes, if requested or opted out | Yes | Yes; consumer is created while target may remain uncreated |
| Can a direct dependency force target creation? | Yes | Yes | Proxy can defer until the target is invoked |
| Creates a new proxy at injection? | Not the nature of the global flag | Not the nature of `@Lazy` on a definition | Yes, a lazy-resolution proxy |
| Calling a singleton target multiple times | Typically one singleton after creation | Same | Proxy typically resolves the singleton target; does not make it prototype |
| How to opt out | `@Lazy(false)` on appropriate beans | Remove `@Lazy` or configure eagerly | Remove `@Lazy` at injection point and consider direct injection |
| Main risk | Errors detected late across a broad scope | This bean's errors may arrive late | Missing target may only surface when invoking the proxy |

Read this table in the context of Spring Boot 3.3.x / Spring Framework 6.1.x. The framework still has infrastructure beans and callbacks that must run at startup; thus **"application-wide lazy" does not mean 100% of objects wait until the first request**.

## 4. Global Lazy: `spring.main.lazy-initialization=true`

Spring Boot supports:

```properties
spring.main.lazy-initialization=true
```

Or in `application.yml`:

```yaml
spring:
  main:
    lazy-initialization: true
```

The configuration is applied while Spring Boot prepares and refreshes the application context. The goal is to **reduce how many beans must be created right at startup**, potentially reducing observed startup time.

It can also be enabled via API:

```java
SpringApplication app = new SpringApplication(DemoApplication.class);
app.setLazyInitialization(true);
app.run(args);
```

This snippet illustrates usage inside the entry point, requiring the `SpringApplication` import and an already-defined `DemoApplication` class. If using `SpringApplicationBuilder`, the corresponding `lazyInitialization(true)` API can be used.

### 4.1. What Can Change

When global lazy is enabled:

- Unneeded application singletons may **not be created at startup**.
- Constructors, `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, and custom init methods of deferred beans run **when the bean is actually created**, not during refresh.
- A web application may defer creating route/controller/service beans until a matching request arrives.
- A configuration or dependency error in a lazy bean may only surface during a first request or a later processing step.

### 4.2. What Is Not Guaranteed

The global flag **does not** guarantee:

- Zero beans are created at startup. Infrastructure beans, mandatory beans, and dependencies of eager beans can still be created.
- Every bean is created **only after the first HTTP request**. Runners, listeners, schedulers, health probes, startup tasks, or other beans may need them earlier.
- Every singleton initially starts as a proxy. Global lazy is mainly a pre-instantiation policy; proxies at injection points are a separate mechanism.
- Less total work for the system. Initialization work may merely **shift from startup to the first execution path**.
- Better request performance. The first request hitting an expensive lazy bean may be slower than normal.
- All configuration errors are deferred. Spring still processes bean metadata/definitions during refresh, and some errors still appear early.

Spring Boot **does not enable application-wide lazy initialization by default**. Official documentation warns that enabling lazy can delay error detection and requires revisiting heap sizing as beans are gradually created while the application runs.

### 4.3. When It Takes Effect

`spring.main.lazy-initialization` is a **context-construction policy**. Changing the property value after the context has refreshed **does not convert already-created singletons into lazy beans**, destroy beans, or automatically build a new context.

To compare enabled vs. disabled, perform **two fresh startups** with different configurations. Editing a properties file while the application is running is not a valid test.

## 5. `@Lazy` on a Bean Definition: Deferring Initialization of One Component

### 5.1. Placing on `@Component`

```java
import org.springframework.context.annotation.Lazy;
import org.springframework.stereotype.Component;

@Component
@Lazy
public class ExpensiveClient {

    public ExpensiveClient() {
        System.out.println("ExpensiveClient constructed");
    }

    public String ping() {
        return "ok";
    }
}
```

Assume the class is within component-scanning scope. When **no eager consumer requests it**, the context can skip creating `ExpensiveClient` during the pre-instantiation phase.

If there is later a call:

```java
ExpensiveClient client = context.getBean(ExpensiveClient.class);
System.out.println(client.ping());
```

then the `getBean` request will **trigger initialization** if the singleton does not yet exist. `@Lazy` does not forbid creating the bean; it only defers it until needed.

The snippet above needs a `context` variable of type `ApplicationContext` or compatible; it is an illustrative snippet, not a complete program.

### 5.2. Placing on `@Bean`

The annotation can be placed on a factory method:

```java
@Configuration
public class ClientsConfig {

    @Bean
    @Lazy
    ExpensiveClient expensiveClient() {
        return new ExpensiveClient();
    }
}
```

This is an **alternative** to `@Component` in the previous example. If you both keep `@Component` and declare the same type via `@Bean` while injecting by single type, you must handle multiple candidates; do not copy both into one application expecting no impact.

For a class provided by a library whose source you cannot edit, declaring `@Bean @Lazy` is usually a straightforward way to control the bean definition.

### 5.3. Placing on `@Configuration`

```java
@Configuration
@Lazy
public class OptionalFeaturesConfig {

    @Bean
    FeatureCatalog featureCatalog() {
        return new FeatureCatalog();
    }

    @Bean
    @Lazy(false)
    RequiredFeatureMetadata requiredFeatureMetadata() {
        return new RequiredFeatureMetadata();
    }
}
```

This is an **annotation illustration**, requiring both `FeatureCatalog` and `RequiredFeatureMetadata` types to exist, plus `Configuration`, `Bean`, and `Lazy` imports. When `@Lazy` is placed on a configuration class, its `@Bean` methods default to lazy; `@Lazy(false)` on a method specifies an eager opt-out per annotation semantics.

**Do not misunderstand:** `@Lazy` on a configuration class is not a lazy flag for the entire Spring Boot application. It affects the relevant configuration scope; the `spring.main.lazy-initialization` property is the `SpringApplication`-level setting.

## 6. `@Lazy` at an Injection Point: Inserting a Proxy to Defer Target Resolution

This is the core of the lesson. Consider constructor injection:

```java
@Component
public class ReportController {

    private final ReportGateway gateway;

    public ReportController(@Lazy ReportGateway gateway) {
        this.gateway = gateway;
    }

    public String report() {
        return gateway.loadReport();
    }
}
```

This snippet requires a `ReportGateway` interface with a `loadReport()` method, along with `Component` and `org.springframework.context.annotation.Lazy` imports. It is an illustrative snippet, not a complete file without defining `ReportGateway`.

The `@Lazy` marker is **placed on the `gateway` parameter**. Within supported autowiring, Spring supplies a **lazy-resolution proxy** for this dependency. That allows `ReportController` to be created **without yet creating or fetching the real `ReportGateway` target**, until a method is invoked through the proxy.

```text
ReportController (may be eager)
       |
       | constructor injection
       v
Proxy implements ReportGateway
       |
       | loadReport() not called yet -> no need to resolve target via this path
       |
       +-- loadReport()
               |
               v
        Resolve ReportGateway bean
               |
               +-- If singleton does not exist yet: create singleton
               +-- Invoke method on real target
```

**This does not have the same effect as `@Lazy` on the `ReportGateway` class.** The annotation on the parameter controls **the consumer's dependency resolution path**. If the target is a normal *non-lazy* singleton and there is no global flag, the container can still independently create the target during refresh due to the target's own pre-instantiation policy.

### 6.1. Example Placing `@Lazy` Only on the Dependency

Suppose:

```java
@Component
class PaymentService {

    PaymentService() {
        System.out.println("PaymentService created");
    }

    void pay() { }
}

@Component
class CheckoutService {

    private final PaymentService payment;

    CheckoutService(@Lazy PaymentService payment) {
        this.payment = payment;
        System.out.println("CheckoutService created");
    }
}
```

This is an illustrative snippet with `Component` and `Lazy` imports. When global lazy is **off** and both bean definitions default to eager singletons, `PaymentService` **can still be created during refresh** despite `CheckoutService`'s constructor receiving a proxy. `@Lazy` on a parameter **does not modify the lazy attribute of the `PaymentService` bean definition**.

Hence the statement "putting `@Lazy` at an injection point means the target will never be created at startup" is **false** when the target remains an eager singleton pre-instantiated independently.

### 6.2. Combining Bean-Definition Lazy with Injection-Point Lazy

When you want the consumer to remain eager while the dependency is only created upon first actual use, combine both:

```java
@Component
@Lazy
class SlowGateway {

    SlowGateway() {
        System.out.println("SlowGateway constructed");
    }

    String fetch() {
        return "ready";
    }
}

@Component
class NormalConsumer {

    private final SlowGateway gateway;

    NormalConsumer(@Lazy SlowGateway gateway) {
        this.gateway = gateway;
    }

    String run() {
        return gateway.fetch();
    }
}
```

This is a valid snippet when both classes reside in a component-scanned package with `Component` / `Lazy` imported. Avoid `final` classes/methods if the dependency type must be class-proxied by Spring.

Role of each annotation:

- `@Lazy` **on `SlowGateway`**: tells the container **not to pre-instantiate** the gateway unless needed.
- `@Lazy` **on `NormalConsumer`'s constructor parameter**: lets the consumer receive a proxy without **forcing gateway resolution inside the constructor**.
- When `normalConsumer.run()` calls `gateway.fetch()` for the first time, the gateway singleton is resolved and created if still missing.

If **`@Lazy` is only on the gateway class** while an eager consumer injects the gateway directly, Spring needs to create the gateway to construct the consumer, defeating the deferral. If **`@Lazy` is only on the parameter** while the gateway remains eager, Spring can still independently create the gateway during refresh.

## 7. Runnable Spring Boot 3.3 / Java 17+ Example: Running Both Global Lazy Modes

To make the difference clear, the example uses:

- `RemoteReportGateway`: a normal singleton, **with no `@Lazy` on its bean definition**.
- `ReportWorker`: a normal singleton, accepting `@Lazy ReportGateway` as a constructor parameter.
- `main`: observes whether **singleton instances** exist before/after retrieving the worker and before/after calling the method.

The exact same source is run **twice in two separate processes**: run 1 with global lazy disabled, run 2 with global lazy enabled. This prevents misunderstandings about object creation timing.

### 7.1. File Structure

```text
lazy-comparison/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          lazy/
            LazyComparisonApplication.java
      resources/
        application.properties
```

`settings.gradle`:

```groovy
rootProject.name = 'lazy-comparison'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

This configures a specific Spring Boot 3.3 version; real environments should choose a maintained version per organizational policy. The project requires a Gradle wrapper or compatible Gradle installation; creating `build.gradle` does not generate `gradlew` automatically.

`src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=ERROR
spring.main.lazy-initialization=false
```

We use app type `NONE` to avoid needing a web server and to prevent web requests or web beans from triggering dependencies before we observe them.

### 7.2. Complete Java Source

File `src/main/java/demo/lazy/LazyComparisonApplication.java`:

```java
package demo.lazy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Lazy;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class LazyComparisonApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                SpringApplication.run(LazyComparisonApplication.class, args)) {

            ConfigurableListableBeanFactory factory =
                    context.getBeanFactory();

            System.out.println("afterRun.gateway="
                    + factory.containsSingleton("remoteReportGateway"));
            System.out.println("afterRun.worker="
                    + factory.containsSingleton("reportWorker"));

            ReportWorker worker = context.getBean(ReportWorker.class);

            System.out.println("afterGetWorker.gateway="
                    + factory.containsSingleton("remoteReportGateway"));

            worker.execute();

            System.out.println("afterExecute.gateway="
                    + factory.containsSingleton("remoteReportGateway"));
        }
    }
}

interface ReportGateway {
    String fetch();
}

@Component
class RemoteReportGateway implements ReportGateway {

    RemoteReportGateway() {
        System.out.println("gateway.constructed");
    }

    @Override
    public String fetch() {
        System.out.println("gateway.fetch");
        return "ok";
    }
}

@Component
class ReportWorker {

    private final ReportGateway gateway;

    ReportWorker(@Lazy ReportGateway gateway) {
        this.gateway = gateway;
        System.out.println("worker.constructed");
    }

    void execute() {
        System.out.println("worker.result=" + gateway.fetch());
    }
}
```

The code above is valid in a **single Java file**: only `LazyComparisonApplication` is a public top-level class; the other three types are package-private. All sit in the `demo.lazy` package so `@SpringBootApplication`'s component scanning finds both `@Component` classes.

**Why use the `ReportGateway` interface?** The injection point has an interface type, allowing Spring to create an interface-based proxy and avoiding issues that arise when proxying a `final` class or non-overridable method. `RemoteReportGateway` is the concrete implementation bean, assigned the default name `remoteReportGateway`; the consumer is named `reportWorker`.

**Why use `containsSingleton`?** `ConfigurableListableBeanFactory.containsSingleton(String)` observes whether the bean factory **already holds an instantiated singleton** under that name. This check is not equivalent to `containsBean` (whether a bean definition exists), and **does not trigger bean creation** just to answer.

The code calls `context.getBean(ReportWorker.class)` after Spring Boot `run` completes. That is a **real bean lookup/creation call** and can initialize the lazy consumer. In the demo, the consumer merely stores the proxy and does not call `fetch` in its constructor, so it does not request the target through the proxy at this point.

### 7.3. Run 1: Global Lazy Off

Run in the project with the Gradle wrapper:

```bash
./gradlew bootRun
```

Because `spring.main.lazy-initialization=false`, both `ReportWorker` and `RemoteReportGateway` are normal singletons. The lines printed by the demo program are:

```text
gateway.constructed
worker.constructed
afterRun.gateway=true
afterRun.worker=true
afterGetWorker.gateway=true
gateway.fetch
worker.result=ok
afterExecute.gateway=true
```

**Output note:** the order **between the two constructor lines** `gateway.constructed` and `worker.constructed` is not a contract to rely on. They may swap depending on bean definition processing order. The `afterRun...` lines only appear after both singletons have been created. From there, the lines printed by `main` and `execute()` match the example order.

Explanation:

- `RemoteReportGateway` **does not carry `@Lazy` on its bean definition**.
- `@Lazy` in `ReportWorker`'s constructor lets the consumer receive a proxy, yet **does not tell the container to skip the gateway's own pre-instantiation**.
- `afterRun.gateway=true` proves the gateway was already a singleton before code called `worker.execute()`.
- `afterGetWorker.gateway=true` does not mean injection proxy behavior failed; it only means the target already existed from eager initialization.

This is the clearest proof that **an annotation at an injection point and the eager/lazy policy of a bean definition are two separate layers**.

### 7.4. Run 2: Global Lazy On

To keep the source unchanged and override runtime config, start a new process with an override:

```bash
./gradlew bootRun --args='--spring.main.lazy-initialization=true'
```

For Gradle and shells with different quoting rules, adjust the quotes accordingly. You can also change the property directly to `true` in `application.properties` and start a new process.

The lines printed by the demo code in this run:

```text
afterRun.gateway=false
afterRun.worker=false
worker.constructed
afterGetWorker.gateway=false
gateway.constructed
gateway.fetch
worker.result=ok
afterExecute.gateway=true
```

Point-by-point explanation:

1. After `SpringApplication.run`, neither application singleton has been requested, so `containsSingleton` returns `false`.
2. Calling `context.getBean(ReportWorker.class)` creates the consumer, printing `worker.constructed`.
3. The constructor receives a **lazy-resolution proxy**, so `RemoteReportGateway` still has no real singleton instance: `afterGetWorker.gateway=false`.
4. When `worker.execute()` calls `gateway.fetch()` for the first time, the proxy resolves the `RemoteReportGateway` bean, its target constructor runs, and it prints `gateway.constructed`.
5. Then the target `fetch()` method runs, and the consumer prints `worker.result=ok`.
6. Finally, `afterExecute.gateway=true` confirms the singleton target now exists.

**Do not overgeneralize this result to every Spring Boot application**: the demo intentionally omits runners, requests, scheduled jobs, and other beans that might use the gateway. If another consumer uses the gateway at startup, the target can still be created before our observation point.

### 7.5. Direct Comparison of the Two Runs

| Observation | Global Lazy Off | Global Lazy On |
| --- | --- | --- |
| Does `ReportWorker` have an instance after `run`? | Yes | Not yet, because nothing requested it |
| Does `RemoteReportGateway` have an instance after `run`? | Yes | Not yet |
| Does retrieving `ReportWorker` via `getBean` create the consumer? | Already exists, just returns it | Yes |
| Does retrieving the consumer force gateway creation via `@Lazy` injection? | No resolution needed at that step; gateway was already eager | No; target remains uncreated |
| Does calling `worker.execute()` use the target? | Yes, target already existed | Yes, proxy creates target before the call |
| What did `@Lazy` on the constructor parameter do? | Proxy was still injected, though target was already eager | Proxy deferred target creation past consumer creation |

A note on instrumentation: logs and `containsSingleton` only reveal state **in the demo**. Use them to learn the mechanics, not as routine deep introspection in production business services.

## 8. Key Experiment: Is `@Lazy` on the Bean Definition Enough?

Assume global lazy is **off**. Mark the gateway:

```java
@Component
@Lazy
class RemoteReportGateway implements ReportGateway {
    // Constructor and fetch() as in main example.
}
```

If `ReportWorker` is created eagerly and **does not have `@Lazy` on its constructor parameter**:

```java
@Component
class ReportWorker {

    private final ReportGateway gateway;

    ReportWorker(ReportGateway gateway) {
        this.gateway = gateway;
    }
}
```

then Spring needs a real `ReportGateway` to complete constructor injection, so **the gateway is created early even though its bean definition carries `@Lazy`**.

This is a crucial case in Spring Framework's lazy singleton documentation: **a lazy bean that is a direct dependency of a non-lazy singleton can still be initialized at startup**.

If you **keep `@Lazy` on the gateway** and **restore `@Lazy` on the worker's parameter** as in the main demo, the consumer can be created eagerly while the target is deferred until the proxy is used.

**Do not use results from the global lazy demo to claim that `@Lazy` on a bean definition alone is enough**: under global lazy, the consumer is also usually lazy, so the eager-dependency scenario may not arise. To test the effect of bean-definition `@Lazy`, run with global lazy off and toggle the annotations on the bean and constructor individually.

## 9. Matrix Table: Two Different Control Knobs

Assume all beans are singletons, the consumer is requested at a given moment, there is no second consumer, and the target is not previously requested by other infrastructure.

| Target Bean Definition | Consumer Injection Point | When Consumer Is Created, Is Target Forced via That Dependency? |
| --- | --- | --- |
| Eager, no `@Lazy` | Direct | Yes, if not already created |
| Eager, no `@Lazy` | `@Lazy` on parameter | **Not via this injection edge**, yet target can still be pre-instantiated independently |
| `@Lazy` on target | Direct | Yes, if consumer needs the real target to instantiate |
| `@Lazy` on target | `@Lazy` on parameter | Usually can be deferred until the proxy is first used |

When the whole application enables lazy initialization, many bean definitions fall into cases similar to row 3 or 4, **yet eager opt-outs and infrastructure beans still exist**. Read the table as an explanatory model of **bean creation policy vs. dependency proxy mechanism**, not a guarantee that all instances appear at the same timestamp.

A very short mnemonic:

```text
@Lazy on BEAN
    -> "Do not create me proactively until needed."

@Lazy on DEPENDENCY
    -> "When creating consumer, pass a proxy first; look up target later."

spring.main.lazy-initialization=true
    -> "Apply lazy policy broadly to eligible beans."
```

## 10. `@Lazy(false)`: Keeping Certain Beans Eager When Global Lazy Is On

Spring Boot allows **designating opt-outs**:

```java
@Component
@Lazy(false)
public class CriticalStartupVerifier {

    public CriticalStartupVerifier() {
        System.out.println("Verifier initialized");
    }
}
```

This snippet requires `Component` and `Lazy` imports and a `CriticalStartupVerifier.java` file inside a scanned package. When global lazy is enabled, a bean definition explicitly marked `@Lazy(false)` can still be initialized eagerly per Spring Boot rules.

Suitable scenarios:

- A critical bean that must detect initialization errors before declaring startup successful.
- An infrastructure component that needs early preparation to avoid unexpected latency on the first request.
- A mandatory check related to readiness or execution prerequisites.

**Do not scatter `@Lazy(false)` everywhere** if your goal is still to defer many beans. Marking too many beans eager forfeits the gains of global lazy, and their eagerness can pull along many dependencies.

### A Trap When Combining `@Lazy(false)` and `@Lazy` at Injection

Suppose `CriticalStartupVerifier` is marked `@Lazy(false)`, while its consumer has:

```java
CriticalConsumer(@Lazy CriticalStartupVerifier verifier) {
    this.verifier = verifier;
}
```

The injection point may receive a proxy; however, **the verifier is an eager bean by its own bean definition** and can still be created during refresh. `@Lazy` on a dependency **does not reverse** the eager decision of the bean definition.

Similarly, if a bean was created earlier because Spring infrastructure needed it, a proxy in another consumer cannot "uncreate" it.

## 11. Lazy Singleton Does Not Mean Prototype or Scoped Proxy

Three concepts frequently mixed up:

| Concept | Question It Answers | Example |
| --- | --- | --- |
| Lazy initialization | **When** is the first instance created? | `@Lazy`, global lazy |
| Bean scope | **How many** instances and how widely shared? | `singleton`, `prototype`, `request` |
| Proxy | **What object does the consumer receive** and how are calls forwarded? | Lazy-resolution proxy, AOP proxy, scoped proxy |

A **lazy singleton** is still a singleton. Once the singleton target is created, subsequent lookups in the same container typically reuse that singleton. `@Lazy` does not turn it into a prototype and does not make it create a new instance on every method call.

At an injection point, a lazy-resolution proxy can behave differently depending on the target's scope. With singletons, Spring normally caches the resolved target; with non-singleton dependencies, resolution can be re-evaluated according to the appropriate lifecycle. When working with request/session/prototype scopes, understand both the scope and the chosen proxy.

**Do not equate a lazy-resolution proxy with `@Scope(proxyMode = ScopedProxyMode.TARGET_CLASS)`**. A scoped proxy serves to inject a bean with a different scope lifecycle into a longer-lived consumer. A lazy-resolution proxy serves to defer dependency resolution. Both can appear in one design, yet they are distinct mechanisms.

## 12. `ObjectProvider` Is an Option When You Need Explicit Retrieval Control

Beyond `@Lazy` at an injection point, Spring provides `ObjectProvider<T>`:

```java
@Component
class ExportService {

    private final ObjectProvider<ReportGateway> gatewayProvider;

    ExportService(ObjectProvider<ReportGateway> gatewayProvider) {
        this.gatewayProvider = gatewayProvider;
    }

    String export() {
        ReportGateway gateway = gatewayProvider.getObject();
        return gateway.fetch();
    }
}
```

This snippet requires importing `org.springframework.beans.factory.ObjectProvider`, `Component`, and the `ReportGateway` interface. It illustrates **intentional target retrieval**.

With `ObjectProvider`, the consumer knows explicitly it holds a **provider**, not a gateway object disguised by a proxy. Calling `getObject()` causes Spring to look up or create the corresponding bean per configuration.

Useful methods:

- `getObject()`: requests the bean; if no suitable target exists, throws an error.
- `getIfAvailable()`: returns the target if present, or `null` when no matching bean exists, per method/version semantics.
- `ifAvailable(Consumer)`: processes the bean if available.
- `getIfUnique()`: useful when you only want the target if there is a unique candidate.

**Be careful:** calling `getIfAvailable()` does not mean "only fetch an already-created singleton." If the bean definition exists and the target is lazy, it can still be created to satisfy the query. A provider defers **until requested**, not a pure cache-inspection API.

### Why `ObjectProvider` Differs from `@Lazy` Injection

`@Lazy` at an injection point returns **an object of the same dependency type**, so the consumer can call `gateway.fetch()` directly. `ObjectProvider` returns **a provider object**, and the consumer chooses when to call `getObject()`.

When a dependency **may be absent**, `ObjectProvider` is usually clearer and safer:

```java
@Component
class OptionalNotifier {

    private final ObjectProvider<NotificationGateway> provider;

    OptionalNotifier(ObjectProvider<NotificationGateway> provider) {
        this.provider = provider;
    }

    void notifyIfConfigured() {
        NotificationGateway gateway = provider.getIfAvailable();
        if (gateway != null) {
            gateway.send();
        }
    }
}
```

This illustration requires a matching `NotificationGateway` interface. With an `@Lazy` injection proxy, even when the real target does not exist, **the proxy can still be injected successfully**, and the missing-target error only surfaces when a method is called. This easily causes surprises for optional dependencies.

## 13. Late-Detected Errors: The Downside of Laziness

A benefit of eager singletons is that Spring catches errors right at startup: missing beans, bad constructors, invalid configuration, connection errors, or broken lifecycle callback code.

When a lazy bean is not created during refresh, errors belonging to **instantiating that bean** may only surface when:

- The first HTTP endpoint invokes the service.
- A scheduled job runs for the first time.
- An `ApplicationRunner` or another bean requests it.
- A listener handles its first event.
- A user accesses a rarely used feature.

Example:

```java
@Component
@Lazy
class BrokenClient {

    BrokenClient() {
        throw new IllegalStateException("Client configuration invalid");
    }
}
```

If nothing requests `BrokenClient` at startup, the app can finish refresh. Afterward, `context.getBean(BrokenClient.class)` exposes the error. This is only an illustration for experimental apps; never intentionally have production beans throw errors like this.

With `@Lazy` at an injection point, a proxy can hide when a missing target is noticed:

```java
@Component
class GatewayConsumer {

    private final MissingGateway gateway;

    GatewayConsumer(@Lazy MissingGateway gateway) {
        this.gateway = gateway;
    }

    void doWork() {
        gateway.execute(); // May fail when using the proxy.
    }
}
```

This snippet illustrates a class requiring a `MissingGateway` interface definition with **no implementation bean registered**. It is not a standalone program; the goal is showing that proxy injection can succeed while method execution fails. If you need to verify a dependency exists at startup, do not treat a proxy as a validation mechanism.

### Do Not Use Global Lazy to "Fix" Bean Errors

If an application previously failed startup due to a missing mandatory dependency, enabling lazy may make the error appear later. That fixes neither configuration nor logic, and is often more dangerous because the service is already receiving traffic.

A sound policy:

1. Identify which beans can safely be lazy.
2. Dependencies critical for correctness should be verified before the application is marked ready.
3. Do not let the first user request act as your integration test.
4. Use readiness/health checks suited to your deployment environment rather than taking short startup time as a sign of application health.
5. In QA, run smoke tests across critical paths to trigger risky lazy beans.

## 14. Performance: Shorter Startup Can Increase First-Request Latency

Suppose `ExpensiveSearchClient` takes 400 ms to create its singleton, and only 5% of requests need that client.

- **Eager**: pays the 400 ms cost during startup; the first request to search does not pay singleton creation cost.
- **Lazy**: may save this cost during startup; the first request invoking search may pay an extra ~400 ms.

These numbers are a **hypothetical scenario**, not a Spring Boot benchmark. Real timings depend on classpath, reflection/proxies, JIT, I/O, dependencies, and system state.

Multiple metrics must be measured:

- Time to `ApplicationStartedEvent` and `ApplicationReadyEvent`.
- Time to true infrastructure readiness.
- P50/P95/P99 latency of the first request and subsequent requests.
- Heap memory at startup and after major features are exercised.
- Number of beans actually initialized.
- First-use failure rate and post-deploy error spikes.

**Trade-off:** laziness usually optimizes **when cost is paid** rather than eliminating it. It can be very useful for short-lived CLIs, rarely used modules, or apps with many optional features; it can be unsuitable for strict-latency services that must be ready on the first request.

### Web Applications and Cold Requests

In Spring MVC or WebFlux, global lazy can leave some controllers/services uncreated when the server starts listening. The first request to a given route can trigger late creation of beans, mappings, or dependencies depending on framework and infrastructure mechanics.

**Do not claim every controller is lazy** solely because of the global flag. Web infrastructure beans still must exist during refresh to register mappings and run the server. Exact rules depend on the Spring Boot version, starters, and configuration.

When using readiness probes, remember readiness evaluates service availability, and does not necessarily exercise every application path to initialize all lazy beans.

## 15. Why Is a Lazy Bean Still Created at Startup?

This is a common debugging question. Typical causes:

1. **An eager consumer** directly constructor-injects the target. The target is needed immediately to build the consumer.
2. **`ApplicationRunner` or `CommandLineRunner`** accesses the target during `run`, before `ApplicationReadyEvent`.
3. **`@PostConstruct`** on an early-created bean invokes the target through a proxy.
4. **A startup event listener** or lifecycle bean requests the target.
5. **`@Lazy(false)`** on the bean or configuration metadata marks it eager.
6. **Framework infrastructure** needs certain beans to handle refresh, post-processing, or routing.
7. **Code explicitly calls `context.getBean(Target.class)`** at startup.
8. **A bean has a complex dependency graph** making it a prerequisite for another bean.
9. **A test fixture** has `@Autowired` in the test class or `@BeforeEach`, retrieving the bean immediately even though production does not at that stage.
10. **A proxy is invoked inside a constructor** or early callback, resolving the target right away.

Debugging requires distinguishing "a **bean definition** exists" from "a **singleton instance** exists." `containsBean` typically returns true when the container knows about the bean, whereas `containsSingleton` tells whether the singleton instance is registered in the cache yet.

### Checking Without Triggering Bean Creation

While diagnosing an active context:

```java
ConfigurableListableBeanFactory factory = context.getBeanFactory();

System.out.println(
        factory.containsSingleton("remoteReportGateway"));
```

This snippet needs a `context` variable of type `ConfigurableApplicationContext` and the `ConfigurableListableBeanFactory` import. `containsSingleton` observes internal singleton state; for prototype/request scopes or differently named beans, it does not replace full introspection.

Avoid using:

```java
System.out.println(context.getBean(RemoteReportGateway.class));
```

to check **whether a bean was already created**, because `getBean` itself can create the lazy bean and alter the state you wanted to observe.

## 16. Design Pitfalls with `@Lazy` on Constructors, Fields, and Setters

### Constructor Parameters Are Preferred Over Field Injection

A clear constructor example:

```java
@Component
class ReceiptService {

    private final ReportGateway gateway;

    ReceiptService(@Lazy ReportGateway gateway) {
        this.gateway = gateway;
    }
}
```

This class snippet requires `ReportGateway` and `Component`/`Lazy` imports. In modern Spring, if a class has only one constructor, `@Autowired` on the constructor is typically unnecessary.

When choosing, answer two separate questions:

- Do you truly need to defer the target?
- Do you truly need to **hold a proxy inside the bean**, or should you inject an `ObjectProvider` to express on-demand retrieval?

If the answer to both is no, use **direct constructor injection** without `@Lazy`, which is easier to read and fails fast.

### Field Injection Works But Is Harder to Test

```java
@Component
class OldStyleReceiptService {

    @Autowired
    @Lazy
    private ReportGateway gateway;
}
```

Requires `Autowired`, `Lazy`, and `Component` imports. This works in a Spring bean, yet hides the dependency in a field, making plain unit test instantiation harder and preventing the field from being `final`. Constructor injection is generally preferred.

### Setter / Injection Methods

Spring also supports lazy on eligible injection points in methods processed by the injection framework. Example:

```java
@Component
class MutableReceiptService {

    private ReportGateway gateway;

    @Autowired
    void setGateway(@Lazy ReportGateway gateway) {
        this.gateway = gateway;
    }
}
```

This snippet requires the corresponding imports. Place the annotation on the **parameter that actually needs to be lazy**, rather than indiscriminately putting `@Lazy` on the entire consumer class when the goal is only deferring one dependency.

## 17. Interactions with AOP Proxies, `@Transactional`, and Circular Dependencies

### A Lazy-Resolution Proxy Is Not an AOP Proxy

A `@Transactional` bean may be wrapped by Spring in an AOP proxy to run the transaction interceptor. An `@Lazy` dependency may also be injected via a lazy-resolution proxy. These are **two different reasons for creating proxies**.

```text
Consumer
   |
   v
Lazy-resolution proxy
   |
   | resolve target
   v
Bean reference (may be an AOP proxy)
   |
   v
Actual bean instance
```

This diagram shows the possibility of multiple intermediate layers, not a promise that every bean has exactly two proxies. When inspecting classes via `getClass()`, do not assume the runtime class matches the class you wrote; a proxy may have a different type.

### `@Lazy` Is Not a Cure-All for Circular Dependencies

Suppose:

```text
ServiceA --constructor--> ServiceB
ServiceB --constructor--> ServiceA
```

Constructor-injection cycles can prevent the application from initializing either bean. `@Lazy` at **one injection point** can sometimes defer one dependency edge and break the immediate creation cycle, because Spring can inject a proxy instead of the real target.

However:

- This does not guarantee all circular dependencies are resolved.
- Either bean calling through the proxy inside its constructor or `@PostConstruct` can re-trigger the cycle.
- Global lazy **does not fix circular dependency structures** when beans ultimately still require each other.
- In Spring Boot, circular reference handling also depends on configuration; do not enable circular dependency support just to bypass design issues.
- It is better to extract shared responsibilities, invert dependencies through interfaces, or organize appropriate events/callbacks.

Using `@Lazy` to defer **a genuinely rarely used dependency** makes sense; using it to mask a circular architecture without understanding the consequences is risky.

## 18. `@Lazy` and Bean Lifecycle Callbacks

While a lazy singleton has not been created, **bean-instance** callbacks have not run yet:

- Constructor.
- Injection into the bean.
- `@PostConstruct`.
- `InitializingBean.afterPropertiesSet()`.
- Custom `initMethod`.
- Certain `BeanPostProcessor` steps tied to bean creation.

When the bean is created on first need, the appropriate steps run at that time before the bean is successfully used.

**Distinguishing `@PreDestroy`:** if a lazy singleton was created and is managed by the container, its corresponding destructor can still run when the context closes normally. If the bean **was never created**, there is no instance on which to invoke the destroy callback. For prototypes, Spring does not automatically manage individual instance destruction the way it does for singletons, whether lazy or not.

Example:

```java
@Component
@Lazy
class LazyCache {

    LazyCache() {
        System.out.println("cache constructed");
    }

    @PostConstruct
    void initialize() {
        System.out.println("cache init");
    }

    @PreDestroy
    void close() {
        System.out.println("cache destroy");
    }
}
```

This snippet requires `Component`, `Lazy`, `jakarta.annotation.PostConstruct`, and `jakarta.annotation.PreDestroy`, and must be registered in a Spring context. If `LazyCache` is not requested, none of the constructor/init/destroy lines appear for that instance. Upon the first `getBean(LazyCache.class)` call, constructor/init run then, and the destructor runs when the context destroys created singletons.

**Do not rely on a lazy bean's `@PostConstruct` to execute mandatory startup tasks.** That bean might not be initialized before the application reaches ready.

## 19. Interaction with `ApplicationRunner` and Readiness Checks

Global lazy can defer many beans until needed. Yet Spring Boot actively locates and invokes `ApplicationRunner` / `CommandLineRunner` during the startup phase **after refresh, before `ApplicationReadyEvent`**.

If a runner injects a service directly:

```java
@Component
class SeedDataRunner implements ApplicationRunner {

    private final SeedDataService seedService;

    SeedDataRunner(SeedDataService seedService) {
        this.seedService = seedService;
    }

    @Override
    public void run(ApplicationArguments args) {
        seedService.seed();
    }
}
```

This is an illustrative snippet requiring `Component`, `ApplicationRunner` / `ApplicationArguments` imports, and a `SeedDataService` bean definition with a `seed()` method.

Even when global lazy is on, Boot still must request the runner to invoke it, and direct constructor injection can pull the service in right before ready. This is expected behavior: **laziness does not override an actual requirement to use the bean**.

If the constructor receives `@Lazy SeedDataService`, yet `run()` immediately calls `seed()`, the proxy only defers creation until **that line inside the runner**, which is still part of startup. Thus time-to-ready may **not improve significantly**.

A system requiring mandatory data initialization before receiving traffic should **deliberately** perform it before ready. Do not try to enable lazy to skip safety conditions and report ready prematurely.

## 20. Testing: Verifying Lazy Policy by Behavior

To test the difference, **operation order** matters.

### Test A: Global Lazy Off

1. Ensure `spring.main.lazy-initialization=false`.
2. Start a fresh context with the Section 7 demo.
3. Before any `getBean` call in observer code, check `containsSingleton("remoteReportGateway")`.
4. The expected result in the demo is `true`, because the target is a non-lazy singleton.

### Test B: Global Lazy On

1. Set `spring.main.lazy-initialization=true` for a fresh run.
2. After `SpringApplication.run`, before `getBean`, the gateway is expected to **have no singleton instance yet** in the demo.
3. Retrieve `ReportWorker`; thanks to the injection proxy, the gateway still does not need to be created.
4. Call `worker.execute()`; the gateway is initialized and the method runs.
5. Verify `containsSingleton` changes from `false` to `true`.

### Test C: Annotation on Bean Definition vs. Injection Point

With global lazy off:

1. Place `@Lazy` on the target gateway.
2. Remove `@Lazy` from the eager consumer's constructor.
3. Observe the target being created to satisfy the constructor dependency.
4. Restore `@Lazy` on the constructor parameter.
5. Compare when the consumer is created vs. when the first method is called.

### Test D: Missing Dependency

1. Create a consumer taking `@Lazy MissingGateway`, without declaring a target bean.
2. Instantiate only the consumer and verify initialization succeeds.
3. Call a method on the proxy and observe the missing-target error.
4. Replace `@Lazy` with `ObjectProvider<MissingGateway>` and use `getIfAvailable()` to handle the optional case with an explicit branch.

Run experiments in an **independent demo project**; do not toggle global lazy on a production service and draw conclusions from a single run.

### Unit Tests and Integration Tests

For a unit test of `ReportWorker`, the simplest approach is passing a fake `ReportGateway` via the constructor and verifying method calls. There is no need to boot a Spring context just to test consumer logic.

For an integration test verifying global lazy policy, boot the context properly with Spring Boot configuration. Test annotations, test fixture beans, or test framework calls can eagerly create targets on their own. When writing assertions, measure **before the test itself injects or calls `getBean` on the target**, otherwise the observation action alters the result.

`ApplicationContextRunner` can be helpful to test bean definitions/configuration in a small context, yet it does not automatically replicate every step of `SpringApplication.run` and Spring Boot's global flag the way a full-startup integration test does unless configured accordingly. Choose the right test scope.

## 21. Symptom-Based Troubleshooting

| Symptom | Common Cause | How to Check / Fix |
| --- | --- | --- |
| Enabled global lazy yet bean still created at startup | Bean opted out as eager, actually needed by a dependency, or called by runner/lifecycle | Identify what requested the bean; inspect dependency graph and callbacks |
| Put `@Lazy` on target yet constructor still runs early | Eager consumer directly constructor-injects target | Move that dependency edge to `@Lazy` injection point if appropriate |
| Put `@Lazy` on constructor parameter yet target still created early | Target bean definition is still eager and pre-instantiated independently | Mark target lazy or selectively enable global lazy |
| `@Lazy` injection succeeds, then missing bean fails on first request | Proxy deferred target resolution | Validate target at startup if mandatory; use `ObjectProvider` if optional |
| After enabling global lazy, first request spikes sharply | Expensive bean is created on the request path | Measure cold path; make critical beans eager or pre-warm |
| Changed lazy property with no effect | Context already refreshed; did not restart | Start a fresh context with the new configuration |
| Added `@Lazy` yet circular dependency still fails | Proxy cannot break an active runtime usage cycle | Redesign dependency graph; avoid calls in constructors |
| `getBean` shows lazy bean "unexpectedly" created | `getBean` itself is the command requesting the bean | Observe via `containsSingleton` before requesting |
| Lazy singleton prints multiple constructor logs | Multiple contexts, different scopes, or multiple bean definitions | Verify bean name, context identity, and scope |
| Lazy bean does not run `@PostConstruct` at startup | Bean has not been created yet | Move mandatory work to an appropriate startup hook |
| Lazy bean does not run `@PreDestroy` on close | Bean was never created or scope does not manage destruction | Check instance/scope and context shutdown path |
| `@Lazy(false)` does not prevent all late errors | Only checks marked eager beans; other beans remain lazy | Identify beans needing fail-fast and verify readiness |
| Proxy hits issues with `final` class / `final` method | Class-based proxy requires proxyable types/methods | Prefer interfaces or evaluate proxy framework limits |
| Shorter startup yet higher total resource usage | Initialization shifted to runtime; heap not provisioned | Measure memory/latency and tune based on real workload |

Practical debugging workflow:

1. **Identify the specific bean** and its bean name in the context; do not broadly say "lazy doesn't work."
2. Determine whether global lazy is on or off in the **current run**.
3. Inspect annotations on both the **bean definition** and the **injection point**; they are two different locations.
4. Find all consumers that can request the target, especially eager beans, runners, listeners, and lifecycle callbacks.
5. Use non-instantiating checks such as `containsSingleton` to inspect instances before calling `getBean`.
6. When an error occurs, distinguish an error **during refresh** from an error **on first proxy invocation**.
7. Measure first-request latency and readiness state; do not make shorter startup time the sole goal.
8. Avoid fixing architecture by sprinkling `@Lazy` everywhere when the dependency graph itself is flawed.

## 22. Misconceptions to Eliminate

**Misconception 1:** "Enabling `spring.main.lazy-initialization=true` means zero beans are created at startup."

False. Infrastructure beans, mandatory beans, and beans accessed during startup can still be created. Global lazy is a **broadly applied policy**, not a ban on creating beans before requests.

**Misconception 2:** "`@Lazy` on a constructor parameter is the same as `@Lazy` on the target class."

False. On a parameter, Spring creates a **lazy-resolution proxy for the dependency**. On the target class, the annotation primarily marks the **bean definition to defer pre-instantiation**.

**Misconception 3:** "Putting `@Lazy` on the target bean ensures no eager consumer can create it before a request."

False. An eager consumer with direct constructor injection can still force immediate target creation. To keep the consumer eager while avoiding immediate target creation, consider placing `@Lazy` on the **injection edge**.

**Misconception 4:** "Putting `@Lazy` at an injection point stops an already-eager singleton target from being created at startup."

False. The target can still be pre-instantiated independently by Spring; the proxy only avoids forcing target resolution **along that injection path**.

**Misconception 5:** "Proxy means every call creates a new bean."

False. Scope still governs lifecycle; a singleton remains a singleton. A lazy-resolution proxy does not turn the target into a prototype.

**Misconception 6:** "If a bean is missing, Spring will always report it when injecting `@Lazy`."

Not necessarily. A proxy can be supplied up front, and the absent target only triggers an error when the proxy attempts to resolve the target.

**Misconception 7:** "Lazy makes the application faster in every case."

Not guaranteed. Initialization cost may shift to the first request or first job; you must measure latency, memory, error detection, and readiness.

## 23. Choosing Solutions for Real Scenarios

### Scenario A: A Rarely Used Integration SDK

For example, a multi-feature application has an analytics SDK called only when users choose a niche feature.

**Suitable approach:** mark the SDK bean `@Lazy`. If an eager consumer injects it directly, consider `@Lazy` on the constructor parameter or inject `ObjectProvider<AnalyticsClient>`. Ensure the first request has timeouts and safe error messages; test the lazy target when the external dependency is unavailable.

### Scenario B: Application with Hundreds of Beans and Very Slow Startup

**Approach to consider:** test `spring.main.lazy-initialization=true` in staging with a representative workload. Measure cold requests and resources, and mark beans that must be ready with `@Lazy(false)`. Do not enable it solely because startup time looks lower in logs.

### Scenario C: Repository Mandatory for Every Main Request

**Suitable approach:** do not blindly defer it if misconfiguring the repository would cause core functionality to fail after the app is marked ready. Consider eager initialization or proactive readiness verification. Keeping critical dependencies fail-fast can be worth more than saving a few hundred milliseconds at startup.

### Scenario D: Optional Dependency That May Be Completely Absent

**Suitable approach:** `ObjectProvider<T>` or explicit interface/strategy/conditional configuration is clearer than an `@Lazy` proxy. A proxy that is always injected is not a signal that the target is guaranteed to be present.

### Scenario E: Circular Dependency Between Two Services

**Suitable approach:** redesign responsibilities and dependency direction. `@Lazy` on one edge can serve as a conscious temporary workaround, yet does not eliminate runtime cycle risks.

## 24. Practice Exercises

### Exercise 1: Classify Annotation Placement

For each snippet, state whether the annotation affects the **bean definition** or an **injection point**:

```java
@Component
@Lazy
class Alpha { }

@Bean
@Lazy
Beta beta() { return new Beta(); }

class Gamma {
    Gamma(@Lazy Alpha alpha) { }
}
```

This is a condensed snippet for analysis; add types and imports when running for real.

Answer: `Alpha` is lazy at its bean definition; the `@Bean` method creating `Beta` is lazy at its bean definition; `Gamma`'s `alpha` parameter is a lazy-resolution injection proxy.

### Exercise 2: Predict First Creation

With `SlowGateway @Lazy` and an eager `Consumer` directly injecting the gateway, is the gateway created during refresh? Why?

Answer: **potentially yes**; if the consumer requires the real gateway to complete constructor injection, the container must create the gateway.

### Exercise 3: Fix Exactly One Dependency Edge

Keep `SlowGateway @Lazy`, change the consumer constructor to `Consumer(@Lazy SlowGateway gateway)`, and do not call the gateway inside the constructor or `@PostConstruct`. Predict when the gateway is created.

Answer: the consumer can be created with a proxy, while the gateway is resolved the first time a method on the proxy is called, assuming no other consumer or infrastructure requests the gateway first.

### Exercise 4: Enable Global Lazy and Observe

Run the Section 7 demo under both configurations. Record the values of:

```text
afterRun.gateway
afterRun.worker
afterGetWorker.gateway
afterExecute.gateway
```

Explain why changing only `spring.main.lazy-initialization` changed the `afterRun` results even though the annotation on `ReportWorker`'s constructor stayed the same.

### Exercise 5: Absent Dependency

Replace the gateway in the consumer with an interface that has no implementation bean, keeping `@Lazy` on the injection point. Observe consumer creation and method invocation. Then switch to `ObjectProvider` and describe how the optional case is handled.

### Exercise 6: First-Request Latency

Create a bean simulating expensive initialization in a test environment, and measure total startup and first/subsequent call times with global lazy on and off. Never put `Thread.sleep(...)` in a production service to simulate "optimization." Separate bean-initialization latency from network/DB latency.

### Exercise 7: Lifecycle of an Unused Bean

Create a `@Lazy` bean with `@PostConstruct` and `@PreDestroy` printing markers. Run twice: once without requesting the bean, once calling `getBean` and then closing the context. Explain why only the second run shows the instance callbacks.

## 25. Pre-Adoption Checklist

- [ ] Clearly distinguished **global lazy**, **bean-definition `@Lazy`**, and **injection-point `@Lazy`**.
- [ ] Have a concrete reason to defer bean creation rather than adding annotations out of habit.
- [ ] Checked whether eager consumers force lazy targets into early creation.
- [ ] Not confusing dependency proxies with the real singleton target in logging/introspection.
- [ ] Not using `@Lazy` to make missing required dependencies look valid.
- [ ] For optional dependencies, considered `ObjectProvider` or explicit conditional configuration.
- [ ] Not assuming global lazy applies to all infrastructure beans.
- [ ] If using `@Lazy(false)`, clearly identified which beans must be eager.
- [ ] Put appropriate measurements in place for startup, first-request latency, throughput, and memory.
- [ ] Tested the failure path when the target is created for the first time.
- [ ] Mandatory startup tasks are not accidentally inside `@PostConstruct` of a bean that might stay uncreated.
- [ ] Have a readiness/health strategy for core dependencies.
- [ ] Tested with fresh contexts rather than drawing conclusions from editing properties after refresh.
- [ ] Not relying on constructor log ordering of independent singletons where the framework makes no ordering contract.
- [ ] Reviewed test setup: test injection, mocks, and fixtures can instantiate beans early.

## 26. Summary

- **Global lazy `spring.main.lazy-initialization=true`** is a broad Spring Boot policy: many beans can be created **on demand** instead of during refresh. It does not guarantee zero beans initialize at startup.
- **`@Lazy` on `@Component` or `@Bean`** primarily changes the **lazy attribute of the bean definition**. That bean is still created if an eager singleton needs it directly.
- **`@Lazy` on a constructor parameter/injection point** makes the consumer receive a **lazy-resolution proxy**, deferring **target resolution across that dependency edge**. It does not automatically change the target's eager policy.
- To create an **eager consumer** while keeping its **target** uninitialized, you must consider **both the target's lazy policy and a proxy at the injection point**.
- `@Lazy(false)` lets critical beans initialize eagerly when global lazy is enabled; `ObjectProvider` fits when you want explicit control over retrieval timing or optional dependencies.
- The goal is not "everything lazy," but **controlled startup-cost optimization** without pushing critical configuration errors and unexpected latency onto users.

### References

- [Spring Boot 3.3 — SpringApplication / Lazy Initialization](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): how to enable `spring.main.lazy-initialization`, benefits/trade-offs, and `@Lazy(false)`.
- [Spring Framework 6.1 — Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/6.1/core/beans/dependencies/factory-lazy-init.html): singleton pre-instantiation and lazy beans requested by eager consumers.
- [Spring Framework 6.1 — @Lazy API](https://docs.spring.io/spring-framework/docs/6.1.17/javadoc-api/org/springframework/context/annotation/Lazy.html): differences between the annotation on bean definitions vs. injection points, lazy-resolution proxies.
- [Spring Framework 6.1 — ObjectProvider API](https://docs.spring.io/spring-framework/docs/6.1.17/javadoc-api/org/springframework/beans/factory/ObjectProvider.html): on-demand bean retrieval, optional/unique target support.
- [Spring Framework — The IoC Container](https://docs.spring.io/spring-framework/reference/core/beans.html): bean definitions, scopes, lifecycle, and dependency injection.
