# Keeping Extension Points Lean, Testable, and Free of Premature Bean Dependencies in Spring Boot

## 1. Why must extension points be designed carefully?

Spring Boot provides many **extension points**: listeners, initializers, post-processors, lifecycle callbacks, runners, and auto-configuration mechanisms. They let you inject logic while the application starts, creates beans, finishes refresh, or shuts down. This power carries a risk: **a callback running earlier in the lifecycle than the developer imagined**.

For example, if a BeanFactoryPostProcessor tries to call a business service to fetch data, that service may be instantiated before required BeanPostProcessors are registered. Mechanisms such as AOP proxies or annotation processing may not be fully applied. The application can boot into a state with hard-to-spot bugs.

Three principles throughout this lesson:

1. **Right phase:** pick the extension point based on the data you need to manipulate and when that data is ready.
2. **Minimal dependencies:** an early bootstrap callback only uses APIs already ready at its stage; never drag in the whole business bean graph.
3. **Small, testable logic:** the callback only acts as a thin adapter to the framework, while calculation/transformation rules live in standalone Java functions or classes.

The goal is writing applications with **predictable startup order, easy fault diagnosis, and smooth Spring Boot upgrades**, rather than creating a single extension class doing too much.

## 2. Distinguishing milestones to pick the right extension point

Before writing a callback, know precisely when it runs. In Spring Boot 3.3.x (Java 17+), the condensed sequence of a successful startup is:

~~~text
SpringApplication.run(...)
    |
    +-- Prepare Environment and Config Data
    |      +-- EnvironmentPostProcessor
    |      +-- early bootstrap events
    |
    +-- Create ApplicationContext
    +-- ApplicationContextInitializer
    +-- Load configuration/BeanDefinition sources
    |
    +-- ApplicationContext.refresh()
    |      +-- BeanDefinitionRegistryPostProcessor
    |      +-- BeanFactoryPostProcessor
    |      +-- Register BeanPostProcessors
    |      +-- Instantiate non-lazy singletons
    |      |      +-- BeanPostProcessor
    |      |      +-- @PostConstruct/InitializingBean
    |      +-- SmartInitializingSingleton (when applicable)
    |      +-- finishRefresh, start SmartLifecycle
    |
    +-- ApplicationStartedEvent
    +-- ApplicationRunner/CommandLineRunner
    +-- ApplicationReadyEvent
    +-- ReadinessState.ACCEPTING_TRAFFIC
    |
    +-- run(...) returns ConfigurableApplicationContext
~~~

The diagram shows **key timing relationships**, not every internal hook and auto-configuration. Some infrastructure beans still must be created before the container finishes registering post-processors. Asynchronous tasks may continue after **run(...)** returns.

**Never confuse "context exists" with "all beans are ready".** ApplicationContextInitializer receives the context before application bean definitions are fully loaded; BeanFactoryPostProcessor works while the container prepares bean configuration; ApplicationRunner runs later, once the context has refreshed.

### Extension point selection table

| Practical need | Appropriate extension point | Should it depend on service beans? |
| --- | --- | --- |
| Modify/add PropertySource at bootstrap | **EnvironmentPostProcessor** | **No**; a full application context has not been created yet |
| Observe events before context exists | Early-registered **ApplicationListener** | **No**; bean-based listeners miss overly early events |
| Configure ConfigurableApplicationContext before loading definitions | **ApplicationContextInitializer** | **No**; prefer Environment and appropriate context APIs |
| Register new BeanDefinitions early | **BeanDefinitionRegistryPostProcessor** | Avoid invoking business beans |
| Modify BeanDefinition metadata | **BeanFactoryPostProcessor** | Avoid calling **getBean()** to instantiate beans |
| Observe/wrap instances during creation | **BeanPostProcessor** | Minimize dependencies because the processor itself is created very early |
| Run work after normal singletons are created | **SmartInitializingSingleton** | Can use appropriate dependencies, though callback still belongs to refresh |
| Coordinate a component needing start/stop | **SmartLifecycle** | Can use reasonable dependencies; avoid unnecessary startup blocking |
| Run synchronous work after refresh and before ready | **ApplicationRunner** or **CommandLineRunner** | **Yes**, suitable for standard dependency injection |
| React when startup reaches ready | **ApplicationReadyEvent** listener | Can use beans, though keep callback short and idempotent when needed |

When only regular bean configuration is needed, **@Bean**, **@ConfigurationProperties**, **@Conditional...**, or Boot's built-in settings are usually simpler than writing a custom extension point.

## 3. Identifying premature bean dependencies

### 3.1. How does early instantiation happen?

Spring must create BeanFactoryPostProcessors and BeanPostProcessors so they can participate in container preparation. If a processor's constructor takes an application service, Spring may have to instantiate that service **before all BeanPostProcessors are registered**.

Example of a risky design:

~~~java
@Component
class AuditBeanPostProcessor implements BeanPostProcessor {

    private final PaymentService paymentService;

    AuditBeanPostProcessor(PaymentService paymentService) {
        this.paymentService = paymentService;
    }
}
~~~

This is an **illustrative snippet**; it assumes **PaymentService** is a declared business bean with matching imports. The risk lies in the **PaymentService** dependency: to construct the processor, Spring must resolve the dependency and may instantiate the service during a very early phase. That service may not yet be eligible for all post-processing, such as transaction auto-proxying or AOP.

Spring Framework emits a classic warning:

~~~text
Bean 'someBean' of type [...] is not eligible for getting
processed by all BeanPostProcessors
(for example: not eligible for auto-proxying)
~~~

This warning should be reviewed alongside the dependency graph. It **does not strictly prove a business flow is already broken**, but indicates the bean was instantiated at a stage where it may not have been fully processed by every BeanPostProcessor.

### 3.2. Avoid calling getBean() inside BeanFactoryPostProcessor

The purpose of **BeanFactoryPostProcessor** is processing **metadata**:

~~~java
BeanDefinition definition =
        beanFactory.getBeanDefinition("reportService");

definition.setLazyInit(true);
~~~

Do not replace this with the following merely to fetch data:

~~~java
ReportService service =
        beanFactory.getBean("reportService", ReportService.class);
~~~

The second snippet can trigger instantiating ReportService right while the BFPP is running. Potential consequences: bypassing some BeanPostProcessors, proxies not yet formed, circular dependencies surfacing early, or broken initialization order.

If you need to modify a **BeanDefinition**, operate on the BeanDefinition. If you need to call a **business service**, choose **ApplicationRunner**, a regular bean, or a callback after the container is fully prepared.

### 3.3. ObjectProvider and @Lazy do not automatically erase lifecycle issues

**ObjectProvider<MyService>** can defer dependency lookup until **getObject()** is called. **@Lazy** can use a proxy or defer instance creation. However, if a bootstrap callback still **calls getObject() or touches the proxy right then**, the bean can still be instantiated too early.

Example:

~~~java
final class StartupHook {

    private final ObjectProvider<ReportService> serviceProvider;

    StartupHook(ObjectProvider<ReportService> serviceProvider) {
        this.serviceProvider = serviceProvider;
    }

    void tooEarly() {
        serviceProvider.getObject().runReport();
    }
}
~~~

This is an illustrative snippet requiring imports and related classes; it shows that **deferring lookup does not help if the developer actively invokes it during an early bootstrap phase**. The fundamental fix remains choosing a callback at the right lifecycle milestone.

## 4. How to design small callbacks with bounded responsibilities

A good extension point is usually a **thin adapter** between Spring Boot and application logic:

~~~text
Spring Boot lifecycle callback
           |
           | extract ready inputs
           v
Pure Java processing function/class
           |
           | return result/metadata
           v
Apply bounded changes to the right API
~~~

Clarify four questions upfront:

1. What is the **input**? Environment properties, bean definitions, application events, or bean instances?
2. What is the **output**? A PropertySource, BeanDefinition, logs/metrics, start/stop decision, or validation result?
3. Which **side effects** are allowed? Only modify the exact target property/bean; never touch unrelated global state.
4. **When must errors block startup?** Distinguish mandatory configuration from auxiliary tasks that can report errors and be handled later.

Useful practices:

- Each callback should have **one primary job**, with a name reflecting its intent.
- Do not turn callbacks into places making HTTP calls, database queries, cache ops, or complex file I/O when bootstrap does not genuinely require it.
- Do not spawn arbitrary background threads inside processors just to avoid waiting; lifecycle and shutdown become hard to manage.
- Only touch bean definitions identified explicitly by name/type, instead of scanning and mutating everything.
- Never print tokens, passwords, or the entire Environment when debugging startup.
- When ordering across multiple processors or runners is needed, use **Ordered**, **PriorityOrdered**, or **@Order** properly and write tests verifying the required order.
- Write logic that can run safely again if the callback fires more than once across multiple ApplicationContexts or repeated test startups.

**Idempotent** means running the same operation again under the same conditions causes no unintended extra effects. For example, adding a PropertySource with a fixed name should check if it already exists; a listener sending a notification for an event should avoid duplicate sends across multiple contexts or retries.

## 5. Choosing the right time to use bean dependencies

### 5.1. Very early phase: Environment and context bootstrap

**EnvironmentPostProcessor** (Spring Boot 3.3) runs before refresh with the contract:

~~~java
void postProcessEnvironment(
        ConfigurableEnvironment environment,
        SpringApplication application);
~~~

Its implementations are normally registered via **META-INF/spring.factories**, not via **@Component** or **@Bean** to receive an application service. Use it to add PropertySources from appropriate config sources; never try to inject beans like Repository or RestClient.

**ApplicationContextInitializer** receives **ConfigurableApplicationContext** before all bean definitions are loaded. It can read Environment, register metadata-level infrastructure components, or configure the context within its contract. This is not yet the place to fetch a service via **context.getBean(MyService.class)**.

Some **ApplicationListener**s receive events before the context is created, such as **ApplicationStartingEvent** or **ApplicationEnvironmentPreparedEvent**. Listeners handling those events must be **pre-registered** via **SpringApplication.addListeners(...)** or an appropriate bootstrap configuration; a **@Bean** listener is only discovered once the container begins processing bean definitions, so it cannot catch all early events.

### 5.2. BeanDefinition processing phase

**BeanDefinitionRegistryPostProcessor** is the extension point to create/remove/modify BeanDefinitions in the registry, while **BeanFactoryPostProcessor** modifies metadata of existing bean definitions. Both run before most regular singleton instantiation.

A lean BFPP may modify just a single definition:

~~~java
@Configuration(proxyBeanMethods = false)
class OptionalReportConfiguration {

    @Bean
    static BeanFactoryPostProcessor optionalReportLazyPolicy() {
        return factory -> {
            if (factory.containsBeanDefinition("optionalReport")) {
                factory.getBeanDefinition("optionalReport")
                       .setLazyInit(true);
            }
        };
    }
}
~~~

This is **a configuration class used inside a Spring Boot application**, assuming a BeanDefinition named **optionalReport** exists. Requires importing **@Configuration**, **@Bean**, and **BeanFactoryPostProcessor**. The code does not fetch instances with getBean, touches no out-of-scope beans, and can be tested using metadata.

**Why static @Bean?** The framework must instantiate BFPPs very early. A **non-static @Bean** can force early instantiation of its enclosing configuration class, causing **@Autowired**, **@Value**, and **@PostConstruct** on the configuration class to miss full lifecycle processing. Spring Framework recommends **static @Bean** for factory methods returning BFPPs.

Similarly, when declaring a **BeanPostProcessor** via **@Bean**, prefer **static** methods, minimal dependencies, and a specific enough return type so Spring detects the processor early.

### 5.3. Late phase: runners and bean lifecycle

**ApplicationRunner** or **CommandLineRunner** is called after context refresh succeeds and before **ApplicationReadyEvent**. They fit using normally DI-injected services, performing required configuration checks, or running short business bootstrap steps.

**SmartLifecycle** fits when a component must **start/stop** with the context lifecycle; note that it may start during refresh, before runners. If a component holds long-lived resources, configure proper shutdown, error handling, and avoid launching unbounded tasks.

**ApplicationReadyEvent** is a milestone later than runners. Listeners handle events synchronously by default, so overly long tasks in a listener can delay readiness completion. Do not confuse **ApplicationStartedEvent** (after refresh, before runners) with **ApplicationReadyEvent** (after runners).

## 6. Runnable Java 17+ example: thin initializer, pure logic, DI-enabled runner

Problem: supply a default **demo.message** value if the operator did not configure one, normalize whitespace in the string, and then print the result in a runner. The bootstrap part **only registers the configuration source**; string transformation is pure Java; the runner **receives injected dependencies after refresh**.

Requirements: **Spring Boot 3.3.x**, **Java 17+**, dependency **spring-boot-starter**, a project with the Spring Boot Gradle plugin. Create file:

**src/main/java/com/example/runtime/LeanExtensionApplication.java**

~~~java
package com.example.runtime;

import java.util.Map;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;

@SpringBootApplication
public class LeanExtensionApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(LeanExtensionApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        app.addInitializers(context -> {
            Map<String, Object> defaults = Map.of(
                    "demo.message", "  Hello   Spring Boot  ");

            context.getEnvironment().getPropertySources()
                   .addLast(new MapPropertySource("demoDefaults", defaults));
        });

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("MAIN | active=" + context.isActive());
        }
    }

    @Bean
    MessageFormatter messageFormatter() {
        return new MessageFormatter();
    }

    @Bean
    ApplicationRunner messageRunner(
            MessageFormatter formatter, Environment environment) {

        return args -> {
            String raw = environment.getRequiredProperty("demo.message");
            System.out.println("RUNNER | " + formatter.normalize(raw));
        };
    }

    static final class MessageFormatter {

        String normalize(String value) {
            if (value == null || value.isBlank()) {
                throw new IllegalArgumentException(
                        "Message must not be blank");
            }
            return value.strip().replaceAll("\\s+", " ");
        }
    }
}
~~~

Run from the project directory with Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

In a run without a **demo.message** value in a higher-priority PropertySource, **the lines explicitly printed by the program** have the expected content and order:

~~~text
RUNNER | Hello Spring Boot
MAIN | active=true
~~~

Framework logs may interleave. Because the example uses **WebApplicationType.NONE**, the context is closed by **try-with-resources** after observation. This lifecycle suits a short CLI program, not a pattern of closing the context right after **run(...)** for a long-running web application.

### 6.1. Why is this initializer safe in the early phase?

The callback:

~~~java
app.addInitializers(context -> {
    context.getEnvironment().getPropertySources()
           .addLast(new MapPropertySource("demoDefaults",
                    Map.of("demo.message", "  Hello   Spring Boot  ")));
});
~~~

only uses the **Environment** already present on the context, creates a small **MapPropertySource** from plain Java data, does not call **context.getBean(...)**, opens no database connections, and requires no repositories or services.

Using **addLast(...)** for the default PropertySource places it at lower priority than existing sources. Thus, values provided by external configuration or CLI can override this default according to normal PropertySource precedence.

To keep PropertySource registration idempotent if the initializer might run again on an Environment, check the name before adding:

~~~java
var sources = context.getEnvironment().getPropertySources();
if (!sources.contains("demoDefaults")) {
    sources.addLast(new MapPropertySource(
            "demoDefaults", Map.of("demo.message", "  Hello   Spring Boot  ")));
}
~~~

This snippet goes **inside the initializer** in an application that already imports MapPropertySource and Map.

### 6.2. Why does normalization logic live in MessageFormatter?

**MessageFormatter.normalize(...)** depends solely on a String input, knowing nothing about SpringApplication, BeanFactory, ApplicationContext, or Environment. Consequently:

- Whitespace, blank input, and Unicode cases can be tested **without starting Spring**.
- Changing formatting rules does not affect how Boot registers the PropertySource.
- You do not have to mock ApplicationContext just to test a string transformation.
- The **Message must not be blank** error comes from isolated logic, testable by a unit test.

Using **@Bean MessageFormatter** is just how pure logic connects to DI. In larger projects, put MessageFormatter in its own file, keeping it independent of Spring APIs.

### 6.3. Why can ApplicationRunner depend on MessageFormatter?

Spring invokes **messageRunner** only after the context has refreshed and required BeanPostProcessors are registered. The runner receives **MessageFormatter** and **Environment** via standard dependency injection; it does not force creating a business service during BeanFactoryPostProcessor or ApplicationContextInitializer.

The **MAIN** line appears after **RUNNER** because **SpringApplication.run(...)** only returns after synchronous runner callbacks complete successfully.

Re-run with arguments:

~~~bash
./gradlew bootRun --args='--demo.message=  Alternate   greeting  '
~~~

Because shells pass whitespace differently, this is a conceptual example; to pass values containing spaces reliably, quote the entire argument appropriately for your shell. For example, on Linux/macOS:

~~~bash
./gradlew bootRun --args="--demo.message='  Alternate   greeting  '"
~~~

The expected output once the argument is passed properly is **RUNNER | Alternate greeting**. Do not use configuration changes to verify lifecycle order if the shell has not passed the value properly.

## 7. Pure Java unit tests and bounded integration tests

### 7.1. Unit tests without creating an ApplicationContext

With **spring-boot-starter-test** (JUnit Jupiter), create file:

**src/test/java/com/example/runtime/MessageFormatterTest.java**

~~~java
package com.example.runtime;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class MessageFormatterTest {

    private final LeanExtensionApplication.MessageFormatter formatter =
            new LeanExtensionApplication.MessageFormatter();

    @Test
    void normalizesExtraWhitespace() {
        String result = formatter.normalize("  Hello   Spring Boot  ");
        assertEquals("Hello Spring Boot", result);
    }

    @Test
    void rejectsBlankMessage() {
        assertThrows(IllegalArgumentException.class,
                () -> formatter.normalize("   "));
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

These tests verify **the exact transformation logic** without opening a web server, loading all auto-configurations, or creating a database. Making the formatter a **static nested class** lets same-package tests instantiate it directly without needing a Spring test runner.

### 7.2. Testing wiring and lifecycle at the right level

The unit tests above do not yet prove Spring Boot invokes the initializer or runner as expected. When integration checks are needed:

- Use **@SpringBootTest** to verify the context actually boots and dependency injection works in a full application.
- Use **ApplicationContextRunner** (from spring-boot-test) to test bean configuration, auto-configuration conditions, or metadata in a lightweight context. **ApplicationContextRunner does not automatically run the full SpringApplication.run flow and ApplicationRunners**; do not expect it to verify events/runners directly.
- If you need to verify a callback truly runs at an early bootstrap milestone, build a minimal **SpringApplication** with the initializer/listener and check its effect on Environment or context afterward.
- Only mock necessary I/O dependencies. Never mock the entire BeanFactory when the real goal is verifying whether Spring recognizes a BeanDefinition/PostProcessor.

**Different tests guard different contracts**: unit tests for algorithms, context tests for wiring/metadata, startup tests for lifecycle ordering. There is no need to test at multiple layers merely to repeat the same assertion.

### 7.3. Example testing a BeanFactoryPostProcessor without forcing bean creation

Suppose a BFPP toggles the lazy flag on definition **optionalReport**. A practical unit test can create a **DefaultListableBeanFactory**, register a **RootBeanDefinition**, invoke the processor on that factory, and check **isLazyInit()**. This does not require instantiating **optionalReport**.

Logical steps:

~~~text
DefaultListableBeanFactory
   -> registerBeanDefinition("optionalReport", ...)
   -> processor.postProcessBeanFactory(beanFactory)
   -> assertTrue(beanFactory.getBeanDefinition("optionalReport").isLazyInit())
~~~

This is a test flow diagram, not standalone Java code. For a BDRPP whose logic depends on multiple other processors, add real-context tests to catch registry ordering issues.

## 8. Avoiding side effects and heavy work inside callbacks

A hook invoked during startup directly affects **startup time**, resilience, and readiness. Tasks to scrutinize:

| Task | Why is it dangerous in an early hook? | Handling strategy |
| --- | --- | --- |
| Calling external HTTP APIs in BFPP | Network timeouts can stall refresh or fail startup | Configure via metadata; run I/O in appropriate runtime services |
| Accessing database in ApplicationContextInitializer | DataSource/Repositories are not fully created yet | Move to a runner or post-refresh service if required for startup |
| Spawning arbitrary threads in BeanPostProcessor | Hard to manage start/stop and test | Use a task executor or a component with explicit lifecycle |
| Printing entire Environment for debugging | Can leak sensitive data and bloat logs | Log only allowed keys, redact secrets |
| Iterating and mutating all BeanDefinitions | Easily affects unintended infrastructure beans | Scope by exact names/types, verify conditions |
| Sending notifications in ApplicationReadyEvent | Can delay readiness or duplicate in multi-context | Keep callback brief, deduplicate, use controlled background handling |

If **a task must finish before the application is ready**, a synchronous runner may be an option, provided it has timeouts, clear error handling, and proper operational criteria. If the task can run after the app is ready, use a service or managed background mechanism rather than holding up an early callback just for convenience.

Do not **swallow exceptions** from mandatory configuration and then report readiness as healthy. Conversely, failures in non-essential auxiliary tasks should follow a defined policy so minor blips do not crash startup for the entire application.

## 9. Rules for error testing and failure milestones

A well-written extension point needs a clear error contract:

**For pure logic:** invalid inputs should throw specific exceptions like **IllegalArgumentException** or return a clearly defined result type. Thoroughly test empty, null, Unicode, duplicate keys, and precedence order.

**For BeanDefinitions:** do not modify a definition when it does not exist; if required, fail clearly with the bean name rather than probing via getBean() and triggering premature instantiation.

**For bootstrap config:** account for property overrides and deployment environments. When providing defaults, use low priority; when enforcing an invariant, validate and fail clearly instead of silently overriding operator settings.

**For runners:** synchronous errors can fail **SpringApplication.run(...)** and publish **ApplicationFailedEvent**. Decide whether a task is truly a startup precondition before placing it in a runner.

**For event listeners:** Spring Boot publishes many events synchronously by default; a very slow listener can delay readiness. In parent/child contexts, a parent listener may receive events from child contexts, so filter by context when events can appear multiple times.

Log **the callback name, lifecycle milestone, relevant bean/property name, and error cause**. Never log sensitive values. When multiple processors operate on the same metadata, document ordering based on **PriorityOrdered/Ordered** or explicit conditions.

## 10. Poor design smells and how to refactor

### 10.1. An initializer with too many responsibilities

**Before:** the initializer reads Environment, calls an auth endpoint, builds a DataSource manually, loads a customer list, and registers multiple singletons directly.

**After:** the initializer only loads or registers bootstrap settings genuinely needed early. Validation/transformation logic moves to pure Java; DataSource is managed by auto-configuration or standard beans; business tasks run at the phase with their dependencies ready.

Benefits: avoids circular dependencies, reduces pre-refresh work, allows step-by-step testing.

### 10.2. BeanPostProcessor depending on a @Transactional service

**Before:** a BPP takes a **@Transactional** **OrderService** via constructor and calls it immediately to fetch a configuration list.

**Problem:** to construct the BPP, OrderService may be instantiated early without full auto-proxying. Transaction/AOP assumptions break.

**After:** extract the small rule set needed by the BPP into a pure Java class or safe metadata without requiring a running service. If calling the real OrderService is needed, do it in a post-refresh callback like a runner or in normal business flows.

Do not try to patch it with **@Lazy** and then invoke the dependency inside the BPP constructor anyway.

### 10.3. BeanFactoryPostProcessor mutating instances

**Before:** a BFPP fetches a bean via **getBean()** and calls setters on the instance.

**After:** if changes are needed before bean instantiation, edit property metadata via **getBeanDefinition()**; if logic must operate on an instance, use an appropriate BPP/lifecycle hook.

### 10.4. Callbacks relying on accidental order

**Before:** two processors edit the same BeanDefinition and expect Spring to invoke them in the order of **@Bean** method names in source.

**After:** separate concerns clearly to avoid overriding each other; declare **Ordered/PriorityOrdered** where needed and test critical ordering. If two steps always execute together, merge them to reduce ordering fragility.

### 10.5. Listener for early events declared with @Component

**Before:** a **@Component ApplicationListener<ApplicationEnvironmentPreparedEvent>** is expected to see the event before the context is created.

**Problem:** the listener bean has not been discovered yet when that early event fires.

**After:** register the listener via **SpringApplication.addListeners(...)** before run or a Boot-supported bootstrap mechanism; if you only need Environment after refresh, pick a later callback and inject dependencies normally.

### 10.6. Very long tasks in ApplicationReadyEvent

**Before:** a ready listener runs data migrations, calls multiple APIs, and populates caches before returning.

**Problem:** event listeners are synchronous by default; readiness gets delayed, and errors are hard to separate from startup.

**After:** if the work is a readiness precondition, place it in a startup step with explicit timeouts, error policy, and timing metrics. If it is not a readiness precondition, move it to a managed background component supporting shutdown and retries.

## 11. Decision framework when implementing a real extension point

Before adding a new extension point, follow this flow:

1. **Identify the goal:** adjust configuration, register a BeanDefinition, modify instances, run startup logic, or manage lifecycle?
2. **Pick the latest necessary early milestone:** a task that can run after refresh does not belong in a BFPP.
3. **List required dependencies:** if Repositories, transaction managers, HTTP clients, or proxied services are involved, prefer late extension points.
4. **Extract pure logic:** accept simple data, return concrete results; do not pass ApplicationContext into every class.
5. **Bound side effects:** modify only targeted beans/properties and handle retries/idempotence.
6. **Design errors intentionally:** what blocks startup, what logs warnings, what is handled later?
7. **Test at the right layers:** unit-test algorithms, context-test wiring/metadata, startup-test callbacks/order when genuinely required.
8. **Monitor runtime:** log concisely and safely, watch for early initialization warnings, and measure startup when needed.

### Self-assessment checklist

- [ ] The callback runs at a stage where its inputs are ready.
- [ ] Does not call **getBean(...)** in BFPP just to access a service.
- [ ] BPP/BFPP registered via **static @Bean** or another valid mechanism when needed.
- [ ] No proxied/AOP services injected directly into early BPPs.
- [ ] Transformation/validation logic can be tested without starting Spring.
- [ ] No out-of-scope BeanDefinitions or PropertySources modified.
- [ ] Ordering among interdependent callbacks has an explicit contract.
- [ ] Event listeners filter by context and avoid duplicate side effects.
- [ ] Errors and timeouts follow clear rules without masking startup failures.
- [ ] Background tasks have shutdown support and do not depend on early callbacks.

## 12. Self-check quiz

**Question 1.** Why shouldn't a **BeanPostProcessor** directly inject a **@Transactional** **PaymentService** in its constructor?

**Answer:** To instantiate the processor early, Spring may create PaymentService before auto-proxying and all BPPs are ready. That risks the service missing full proxy/annotation processing as expected.

**Question 2.** Does **ObjectProvider<PaymentService>** completely fix early instantiation if a BFPP calls **getObject()** immediately inside its callback?

**Answer:** No. ObjectProvider only defers dependency retrieval; calling getObject() early still instantiates the service prematurely.

**Question 3.** You need to set **BeanDefinition.setLazyInit(true)** on a specific bean before it is instantiated. Should you use BFPP or ApplicationReadyEvent?

**Answer:** **BeanFactoryPostProcessor**; ApplicationReadyEvent arrives after the context has refreshed, which is too late to alter initialization metadata of already-created singletons.

**Question 4.** To verify whether the whitespace-normalization algorithm is correct, do you need @SpringBootTest?

**Answer:** No. Testing **MessageFormatter.normalize** directly with JUnit suffices for that algorithm. Separate integration/startup tests are needed when verifying how Spring invokes initializers/runners.

**Question 5.** Is a **@Bean ApplicationListener<ApplicationStartingEvent>** guaranteed to see that run's starting event?

**Answer:** No. The starting event fires before the context holding the listener bean is created and registered. You must register the listener before **run(...)** starts.

**Question 6.** Does having an ApplicationRunner receive a service via constructor injection and run before **ApplicationReadyEvent** fit the lifecycle?

**Answer:** Yes. Runners are beans invoked after refresh, once standard dependency injection is established; a runner's synchronous work must finish before the Ready milestone of a successful startup.

**Question 7.** Should a callback adding a PropertySource with default values use **addFirst** so it always beats all operator settings?

**Answer:** Normally no. For default values, use a low priority like **addLast** so operator configurations can still override them.

**Question 8.** If **ApplicationContextRunner** creates your bean, does that prove **ApplicationRunner.run** executed?

**Answer:** No. ApplicationContextRunner tests context/configuration; it does not reproduce SpringApplication's full runner invocation mechanism. Verifying that milestone requires a corresponding startup test.

## 13. Takeaways and official documentation

Good extension points in Spring Boot **sit at a sensible lifecycle milestone, consume only ready dependencies, and focus on one specific job**. Early callbacks such as **EnvironmentPostProcessor**, **ApplicationContextInitializer**, **BeanDefinitionRegistryPostProcessor**, and **BeanFactoryPostProcessor** should primarily operate on Environment/metadata. BeanPostProcessors also need minimal dependencies to avoid pulling services into bean creation too early.

When full DI business logic is needed, prefer late callbacks like **ApplicationRunner** or regular services. Separating algorithms into pure Java makes unit testing fast, while integration tests independently verify framework contracts. This design reduces hard-to-diagnose startup bugs and improves maintainability and testability.

Official reference sources (Spring Boot 3.3 / Spring Framework 6.1):

- Spring Framework — Container Extension Points: https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html
- Spring Boot — SpringApplication, Application Events and Listeners, ApplicationRunner: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — EnvironmentPostProcessor API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/env/EnvironmentPostProcessor.html
- Spring Boot — Customize the Environment or ApplicationContext Before It Starts: https://docs.spring.io/spring-boot/how-to/application.html
- Spring Framework — ApplicationContextInitializer API: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/context/ApplicationContextInitializer.html
- Spring Boot 3.3 — ApplicationRunner API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html