# Why Conditions Should Not Instantiate Beans or Perform Tasks with Side Effects

## 1. The Problem: Configuration Decisions Differ from Business Execution

In Spring, a condition attached via `@Conditional` helps the framework decide **whether to register a component/BeanDefinition**. In Spring Boot, mechanisms such as `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnBean`, and `@ConditionalOnMissingBean` are built on this idea so auto-configuration contributes beans only when appropriate.

Conditions are not the place to instantiate application objects, open network connections, send messages, update databases, or run background tasks. The reason is not merely "clean code"; **condition evaluation occurs while Spring is assembling the container structure, before beans have a complete lifecycle**.

The important contract specified by Spring Framework for the `Condition` interface:

> Conditions are checked immediately before the bean-definition is due to be registered and are free to veto registration based on any criteria that can be determined at that point; conditions must follow the same restrictions as `BeanFactoryPostProcessor` and take care to never interact with bean instances.

The proper separation:

~~~text
                 CONFIGURATION / REGISTRATION PHASE
  read @Configuration, @Bean, @Import, annotation metadata
                             |
                             v
                 @Conditional -> matches(...)
                             |
                  +----------+----------+
                  |                     |
                true                  false
                  |                     |
                  v                     v
      Allow bean definition      Skip that bean /
      to be registered           configuration definition
                  |
                  v
                  CONTAINER INITIALIZATION PHASE
            dependency injection, BeanPostProcessor,
          @PostConstruct, initMethod, proxy/lifecycle
                  |
                  v
                   BEAN READY TO OPERATE
      ApplicationRunner / events / requests / schedulers
~~~

An ideal condition is **a check based on already available information** answering "should this be registered?"; real work happens in lifecycle-managed components after the decision has been made.

## 2. The Practical Contract of `Condition.matches`

The interface in Spring Framework:

~~~java
package org.springframework.context.annotation;

import org.springframework.core.type.AnnotatedTypeMetadata;

@FunctionalInterface
public interface Condition {
    boolean matches(
        ConditionContext context,
        AnnotatedTypeMetadata metadata
    );
}
~~~

*This is a condensed API signature for study, not a file you need to define yourself.*

- `context`: provides `Environment`, `BeanDefinitionRegistry`, `BeanFactory` (which may be unavailable in some contexts), class loader, and resource loader.
- `metadata`: annotation details of **the class or method currently being evaluated**; not a bean instance.
- `true`: this condition permits registration **to proceed**, though other conditions may still veto it; a bean instance is not necessarily created yet.
- `false`: the component carrying this condition is not registered during this configuration pass.
- If multiple conditions apply together, logically **all must pass** (AND). Conditions should be independent and not use evaluation order as a data channel.

A good example, reading only a property:

~~~java
package sample.condition;

import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class EnabledCondition implements Condition {
    @Override
    public boolean matches(
        ConditionContext context,
        AnnotatedTypeMetadata metadata
    ) {
        return context.getEnvironment()
            .getProperty("sample.feature.enabled", Boolean.class, true);
    }
}
~~~

This condition reads configuration at check time and returns a `boolean`. It does not `new` up business objects, request other beans, or allocate external resources.

**Note on sample correctness:** the `Boolean.class` property type and default `true` use `Environment`'s conversion mechanism. If the property has an invalid unconvertible value, a configuration error may result; do not assume every arbitrary string is safely interpreted as `false`.

## 3. First Hazard: Beans Are Not Ready for Use Yet

### The Container Is Still Under Construction

While Spring is processing `@Configuration` or registering bean definitions, initialization of the entire context is not necessarily complete. Some beans are still **uncreated**, have not received dependencies, have not passed through `BeanPostProcessor`s, or have not run initialization callbacks.

Calling `getBean(...)` inside `matches(...)` can force premature bean creation:

~~~java
// ANTI-PATTERN — do not use inside a condition.
@Override
public boolean matches(
    ConditionContext context,
    AnnotatedTypeMetadata metadata
) {
    Object remoteClient =
        context.getBeanFactory().getBean("remoteClient");
    return remoteClient != null;
}
~~~

Problems:

1. `getBeanFactory()` is not always available and can return `null`.
2. The `remoteClient` bean might not have a definition yet; calling `getBean` throws an exception.
3. If a definition already exists, `getBean` can trigger **instance initialization** before the container has finished preparing.
4. That instance may miss full post-processing, proxies, and configuration the application expects.
5. The condition can create a dependency cycle: to decide bean A, it forces creating B; meanwhile B depends on A or on configuration currently gated by the condition.

Even if the snippet occasionally appears to "work", it violates the meaning of a condition and can break when processing order changes, auto-configurations are added, or Spring versions change.

### Do Not Confuse `BeanDefinition` with a Bean Instance

| Object / operation | Meaning | Appropriate in a condition? |
| --- | --- | --- |
| `AnnotatedTypeMetadata` | Annotation metadata of the class/method | Yes |
| `Environment#getProperty(...)` | Currently available configuration value | Usually yes |
| `ClassLoader` / `ResourceLoader` | Classpath/resource information | Yes, for lightweight lookups without side effects |
| `BeanDefinitionRegistry` | Metadata of definitions registered up to this point | Possibly, with phase/order awareness |
| `BeanFactory#getBean(...)` | May create and return a bean **instance** | **No** |
| `ApplicationContext#getBean(...)` | Fetches an instance; can trigger bean creation | **No** |
| Directly calling `new SomeService(...)` | Instantiates an object outside the container | **No**, if it is a business/resource object |

**Conclusion:** if the goal is to check whether a bean *has already been registered as a definition*, use Boot's specialized conditions like `@ConditionalOnBean`/`@ConditionalOnMissingBean` where appropriate. Do not fetch bean instances to "test existence".

## 4. Second Hazard: Premature Instantiation Breaks the Lifecycle

Suppose a bean requires these steps:

~~~text
Instantiate object
 -> inject dependencies/configuration properties
 -> BeanPostProcessor before initialization
 -> @PostConstruct / InitializingBean / initMethod
 -> BeanPostProcessor after initialization
 -> AOP proxy if applicable
 -> use in application
~~~

If a condition forces bean creation during the configuration decision stage, critical setup steps may not have finished yet or may be bypassed at the wrong moment. Consequences vary by case:

- Values from `@ConfigurationProperties`/binding have not been applied as expected.
- `@Transactional`, caching, security, or AOP proxies have not been created or attached properly.
- The bean is used before its collaborators are ready.
- `BeanFactoryPostProcessor`, `BeanPostProcessor`, or other configurations have not completed their related work.
- Messages about beans being "not eligible for getting processed by all BeanPostProcessors" or hard-to-trace circular dependency errors may appear.

**This does not claim every early `getBean` call will always lack proxies or binding**; these are **real timing-dependent risks**. The fundamental flaw is that the condition deliberately pulled bean instantiation out of its normal lifecycle progression.

### Related Warning in Spring Boot: SpEL Calling a Bean

An easily overlooked example is an expression condition referencing a bean:

~~~java
// ANTI-PATTERN of design intent.
// @ConditionalOnExpression("@remoteProbe.check()")
~~~

Spring Boot documentation warns that referencing a bean in SpEL inside `@ConditionalOnExpression` can cause that bean to be instantiated very early, leaving it ineligible for post-processing (such as configuration property binding) and in an incomplete state. Therefore, **do not call bean methods in SpEL as a substitute for metadata conditions**. When you only need a property, use `@ConditionalOnProperty` instead.

## 5. Third Hazard: Side-Effecting Operations Have No Run-Once Guarantee

A **side effect** is any observable behavior beyond returning the `boolean`: writing files, sending HTTP requests, altering database rows, publishing messages, mutating static variables, scheduling tasks, opening sockets, consuming a message from a queue, etc.

A conceptually wrong condition:

~~~java
// ANTI-PATTERN — do not use in applications.
public boolean matches(
    ConditionContext context,
    AnnotatedTypeMetadata metadata
) {
    chargeCreditCard();
    return true;
}
~~~

*This is pseudocode: `chargeCreditCard()` is undeclared; it only illustrates what is forbidden.*

Why is it wrong?

- Spring calls `matches` while processing configurations, **providing no contract that the method is ever called strictly once**.
- Multiple configurations or context-building passes can trigger multiple checks.
- Data can change between calls; side effects stop the condition from being a predictable check.
- If the bean is ultimately blocked by another condition, a side effect from an earlier condition may **have already occurred**.
- A startup failure after the condition ran does not roll back file edits, HTTP requests, emails, or transactions in external systems.
- In test suites, every test context or configuration attempt may invoke the condition again, causing unintended repeated actions.

An especially dangerous example:

~~~java
// ANTI-PATTERN — do not use in conditions.
static int checks = 0;

public boolean matches(
    ConditionContext context,
    AnnotatedTypeMetadata metadata
) {
    checks++;
    return checks == 1;
}
~~~

The first call returns `true`, the next `false`; with identical input configuration, the outcome changes depending on how many times the framework invoked it. This is code built on **hidden state and execution order**, notoriously creating hard-to-reproduce bugs.

A log statement for diagnostics is a mild side effect; it may be considered if genuinely needed, yet **correct logic must never depend on log line counts or log order**, and avoid logging secrets or doing heavy I/O inside conditions.

## 6. Fourth Hazard: Unstable Condition Outcomes

A condition should produce **results stable with respect to the configuration data supplied for that processing pass**. Avoid querying external state that can fluctuate millisecond by millisecond, especially performing network checks:

~~~java
// ANTI-PATTERN — making outcomes depend on the network.
public boolean matches(
    ConditionContext context,
    AnnotatedTypeMetadata metadata
) {
    return pingProductionDatabase(); // Not implemented here.
}
~~~

Reasons to avoid this:

1. **The network may not be ready at startup.** A transient connection blip can drop the bean, even though the application ought to start and wait for its dependency to recover.
2. **Slow startup** when requests time out or DNS fails.
3. **Conflating configuration errors with availability failures.** An unresponsive service at startup second does not mean the bean definition should not exist.
4. **Conditions can be evaluated across different phases/contexts**; inconsistent answers make the system unpredictable.
5. **No automatic refresh:** once the condition returns false and the bean is skipped, when the external service recovers, Spring does not re-register the bean just because the outage ended.

If you genuinely want a feature created only when a property is set, evaluate **the property**. If you must track service connectivity, create the bean in a stable configuration and use health checks, retries, circuit breakers, or appropriate lifecycle mechanisms.

### Distinguishing Metadata from Operational State

- **Metadata suited for conditions:** "does the dependency JAR contain this class?", "is the property enabled?", "which profile is active?", "is the configuration resource present?".
- **Runtime state belongs elsewhere:** "is the database accepting connections?", "has a job sent the email?", "is the API returning 200 right now?", "how many events have been consumed?".

Not all read I/O is strictly forbidden by API syntax, yet **I/O with latency, failures, mutable state, or side effects** is bad design for definition registration decisions.

## 7. Fifth Hazard: Registration Order and Circular Dependencies

Bean definitions are processed progressively as Spring parses configurations. A condition reading the registry sees only **the state processed at the moment of inspection**, not necessarily the complete final set of bean definitions.

Example of a custom condition doing this:

~~~java
// STILL REQUIRES GREAT CAUTION:
boolean present =
    context.getRegistry().containsBeanDefinition("mailClient");
return present;
~~~

The statement above checks a **definition** rather than instantiating an instance, so it does not commit the exact same error as `getBean`. However, its result can be order-dependent: the `mailClient` bean might not be registered yet when the condition runs, even though it will be registered by a class processed afterward.

With Spring Boot, `@ConditionalOnBean` and `@ConditionalOnMissingBean` have framework-defined semantics. Boot documentation recommends using them primarily in auto-configuration, since auto-configurations are processed after user bean definitions. Even so, these conditions still rely on definitions **processed up to evaluation time**; ordering among auto-configurations still matters.

**Do not fix a missing-definition problem by calling `getBean`**, because that method goes much further: it can instantiate objects when the container is not ready. Instead, fix the configuration layering, declare auto-configuration ordering relationships where appropriate, or use Boot annotations with matching semantics.

## 8. Design Rules: What Characterizes a Good Condition?

To keep conditions easy to test and maintain:

1. **Read only necessary data.** Prefer `Environment`, annotation metadata, classpath/resource metadata, or existing definitions via appropriate APIs.
2. **Do not create business instances.** Never call `getBean` or `new` up services/database clients just to decide registration.
3. **Do not mutate state.** Avoid writing files, publishing events, calling state-changing endpoints, incrementing business counters, or scheduling tasks.
4. **Do not depend on call count.** Spring can check `matches` in varying circumstances.
5. **Do not rely on ambiguous ordering.** Conditions reading registry state must understand phases and already processed definitions.
6. **Run fast and reliably.** Avoid networking, databases, slow I/O, and timeouts.
7. **Stay easy to reason about.** Identical configuration and metadata should produce identical logical outcomes.
8. **Use built-in conditions when available.** In Boot, `@ConditionalOnProperty`/`@ConditionalOnClass`/`@ConditionalOnMissingBean` are usually safer and clearer than hand-written conditions.

Do not equate a **pure condition** with "forbidden from using any API". Looking up a property in `Environment` is valid; the danger lies in **wrong-lifecycle instantiation, side effects, mutable state, and premature assumptions about the container**.

## 9. Runnable Example: Pure Condition, Timely Bean Instantiation

This section is a console Spring Boot **3.3.13 + Java 17 + Maven 3.9+** application needing no HTTP server. The example intentionally uses `@Lazy` to separate two moments:

- **Bean definition registration**: decided by `@Conditional`.
- **Bean instance creation**: only when the program requests the bean via `getBeanProvider(...).getIfAvailable()`.

We use a counter in the **bean's constructor** to observe instantiation timing. This is an illustration tool in the application; **do not place or increment counters inside `Condition.matches`**.

### 9.1. Directory Tree

~~~text
safe-condition-demo/
├── pom.xml
└── src/main/java/example/
    ├── app/
    │   └── DemoApplication.java
    ├── config/
    │   └── FeatureConfiguration.java
    ├── condition/
    │   └── FeatureEnabledCondition.java
    └── service/
        └── CountedService.java
~~~

The packages under `example.config`/`example.condition`/`example.service` sit **outside** the default component scan from `example.app`. We use `@Import(FeatureConfiguration.class)` to be certain the configuration class is processed without widening unrelated scanning.

### 9.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>safe-condition-demo</artifactId>
    <version>1.0.0</version>
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
~~~

### 9.3. `src/main/java/example/condition/FeatureEnabledCondition.java`

~~~java
package example.condition;

import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class FeatureEnabledCondition implements Condition {

    @Override
    public boolean matches(
        ConditionContext context,
        AnnotatedTypeMetadata metadata
    ) {
        return context.getEnvironment().getProperty(
            "demo.feature.enabled", Boolean.class, true
        );
    }
}
~~~

That is the entire condition: one property read returning a boolean. No `getBean`, no JDBC/HTTP, and no mutable variables.

### 9.4. `src/main/java/example/service/CountedService.java`

~~~java
package example.service;

import java.util.concurrent.atomic.AtomicInteger;

public final class CountedService {
    private static final AtomicInteger CREATED =
        new AtomicInteger();

    public CountedService() {
        CREATED.incrementAndGet();
    }

    public static int createdCount() {
        return CREATED.get();
    }

    public String value() {
        return "ready";
    }
}
~~~

This is a regular Java bean. `CREATED` merely demonstrates **how many times the constructor ran inside the same JVM**. The `java -jar` commands below are separate processes, so each run starts with counter 0. Do not use this counting pattern to design real conditions.

### 9.5. `src/main/java/example/config/FeatureConfiguration.java`

~~~java
package example.config;

import example.condition.FeatureEnabledCondition;
import example.service.CountedService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;

@Configuration(proxyBeanMethods = false)
public class FeatureConfiguration {

    @Bean
    @Lazy
    @Conditional(FeatureEnabledCondition.class)
    public CountedService countedService() {
        return new CountedService();
    }
}
~~~

- `@Conditional` decides whether to register the `countedService` definition.
- `@Lazy` asks that this singleton bean not be instantiated solely because the container starts up, provided no other component forces its use.
- Only the factory method calls `new CountedService()` **after the bean is requested**; it is not inside the condition.
- `proxyBeanMethods=false` fits because the configuration does not cross-call factory methods.

### 9.6. `src/main/java/example/app/DemoApplication.java`

~~~java
package example.app;

import example.config.FeatureConfiguration;
import example.service.CountedService;
import org.springframework.boot.Banner;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Import;

@SpringBootApplication(scanBasePackages = "example.app")
@Import(FeatureConfiguration.class)
public class DemoApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                 new SpringApplicationBuilder(DemoApplication.class)
                     .web(WebApplicationType.NONE)
                     .bannerMode(Banner.Mode.OFF)
                     .run(args)) {

            boolean definition = context.getBeanFactory()
                .containsBeanDefinition("countedService");

            int beforeLookup = CountedService.createdCount();

            CountedService service =
                context.getBeanProvider(CountedService.class)
                    .getIfAvailable();

            System.out.println("definition=" + definition);
            System.out.println("constructedBeforeLookup=" + beforeLookup);
            System.out.println("service=" +
                (service == null ? "none" : service.value()));
            System.out.println("constructedAfterLookup=" +
                CountedService.createdCount());
        }
    }
}
~~~

`WebApplicationType.NONE` keeps the example in console mode without starting an embedded HTTP server. `containsBeanDefinition` checks the **definition**, without fetching an instance. Only `getIfAvailable()` asks the container to instantiate `CountedService`.

### 9.7. Running and Comparing Output

In the `safe-condition-demo` directory:

~~~bash
java -version
mvn -version
mvn -q clean package
java -jar target/safe-condition-demo-1.0.0.jar
~~~

Four lines from the program's `System.out.println` statements:

~~~text
definition=true
constructedBeforeLookup=0
service=ready
constructedAfterLookup=1
~~~

Explanation:

1. `matches` is evaluated based on the default property `true`.
2. The `BeanDefinition` of `countedService` exists.
3. Because the bean is `@Lazy`, the constructor has not run at `beforeLookup`.
4. `getIfAvailable()` requests the bean, and Spring instantiates an instance.
5. The counter increments to 1; the condition **is not what triggered instantiation**.

Disable via property:

~~~bash
java -jar target/safe-condition-demo-1.0.0.jar --demo.feature.enabled=false
~~~

Four lines printed by the program:

~~~text
definition=false
constructedBeforeLookup=0
service=none
constructedAfterLookup=0
~~~

Because the condition fails, Spring does not register the `countedService` bean definition. The provider returns `null` and no instance is created.

Enable explicitly:

~~~bash
java -jar target/safe-condition-demo-1.0.0.jar --demo.feature.enabled=true
~~~

The output returns to matching the default run.

**Limitation of evidence:** the counter used in this example does not measure how many times `matches` was invoked. The task requires side-effect-free conditions, so we do not install a counter inside `matches` just to count evaluations.

### Table Distinguishing Both Moments

| Scenario | Bean definition after startup | Instances before lookup | Instances after lookup |
| --- | --- | --- | --- |
| Property omitted (enabled by default) | Present | 0 | 1 |
| `demo.feature.enabled=true` | Present | 0 | 1 |
| `demo.feature.enabled=false` | Absent | 0 | 0 |

Do not infer from `definition=true` that an instance already exists: `@Lazy` is a clear counterexample. And do not infer that every condition runs only once because the example creates exactly one instance; those are **two separate contracts**.

## 10. Small Variations to See Behavior Clearly

### Experiment A: Remove `@Lazy`

In `FeatureConfiguration`, delete `@Lazy` and its import, then rebuild:

~~~bash
mvn -q clean package
java -jar target/safe-condition-demo-1.0.0.jar
~~~

When conditions pass, a default singleton bean is normally instantiated during context refresh. Expected output:

~~~text
definition=true
constructedBeforeLookup=1
service=ready
constructedAfterLookup=1
~~~

Key takeaway: **the constructor ran earlier due to scope/lazy policy**, not because `matches` was allowed to create beans itself.

### Experiment B: Move the Condition to Class Level

Move `@Conditional(FeatureEnabledCondition.class)` from the method up to `FeatureConfiguration`. When property=`false`, the entire configuration is skipped. If the configuration had other `@Bean`/`@Import` declarations, they too are governed by the class-level condition.

If you only want to disable `CountedService`, keep the condition on the method. Condition scope and bean instantiation timing are two independent dimensions.

### Experiment C: Deliberately Inject the Service into Another Bean

Add an eager singleton bean that depends on `CountedService` (only when the condition is enabled). When Spring creates it at startup, the dependency can cause `CountedService` to be instantiated early **even though it has `@Lazy` on its factory method**. Thus `@Lazy` is not a guarantee of "never instantiated before main's lookup"; an eager dependency can request the bean.

This exercise helps distinguish **valid container dependency resolution** from **invalid behavior when a condition calls getBean itself**.

### Experiment D: Switch the Condition to Boot's Built-in Annotation

Replace:

~~~java
@Conditional(FeatureEnabledCondition.class)
~~~

with:

~~~java
@ConditionalOnProperty(
    prefix = "demo.feature",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
~~~

Remember to import `org.springframework.boot.autoconfigure.condition.ConditionalOnProperty`. For the three cases true/false/missing property, the result matches the main example. However, keep in mind Boot's condition has its own value conversion rules; do not equate the implementation with `Environment#getProperty(..., Boolean.class, true)` across every possible input string.

The benefits are less custom code, standardized semantics, and support from Boot's condition reporting.

## 11. Where Should Side Effects Live When the App Actually Needs to Do Work?

### Resource Initialization: Put It in Beans and Lifecycle

If you need to create a client or connection, the bean factory method, constructor, or appropriate initialization hook is the place to do it. Consider connection timing, retries, and resource closing; **do not put those steps inside `matches`**.

Example configuring a service with properties:

~~~java
@Configuration(proxyBeanMethods = false)
class ClientConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "client",
        name = "enabled",
        havingValue = "true"
    )
    ExternalClient externalClient(ClientProperties properties) {
        return new ExternalClient(properties.url());
    }
}
~~~

*This is an illustrative snippet requiring `ExternalClient`, `ClientProperties`, and corresponding imports; not a standalone file.* The condition only decides whether to register the bean; constructing the client happens in the Spring-managed factory method.

### Tasks After the Application Is Ready: `ApplicationRunner`

When an application needs to run a task after startup, declare an `ApplicationRunner`:

~~~java
@Bean
ApplicationRunner warmupRunner(CacheWarmer warmer) {
    return args -> warmer.preload();
}
~~~

*This is an illustrative method requiring `CacheWarmer`/imports, not a full program.* Spring Boot executes runners after the context has refreshed, at the stage when it is ready to run application tasks. Side-effecting operations belong in the runner's body, **not inside conditions**.

For tasks requiring system-wide once-only execution in distributed systems, `ApplicationRunner` by itself **does not guarantee global exactly-once**: every instance starting up can run it. Use idempotency, transactional outbox, job locks, or an appropriate coordination mechanism.

### Checking System Health: Health Indicator / Readiness / Retry

If a feature depends on a live external system:

- Use stable feature flags/properties to decide bean definitions.
- Let the bean own connections and retry/circuit-breaker policies.
- Use health/readiness probes to report whether the service is ready to serve.
- If unready, return appropriate status errors or defer execution at the business layer.

Do not turn **"the external service happened to be down during one check"** into a permanent decision not to register the bean in a running context.

### Scheduled Work: Register via Lifecycle/Scheduler

If scheduling is needed, let Spring create the scheduler/task with valid configuration, then manage start/stop via lifecycle. Conditions can decide **whether the scheduler bean is registered**; they should not spawn threads or register cron jobs every time `matches` is called.

## 12. Why Does Writing a "Bean-Reading" Condition Easily Cause Circular Dependencies?

Consider the model:

~~~text
To register bean A:
    ConditionForA.matches(...)
         |
         +-- calls getBean("B")
               |
               +-- creates B -> needs A
                    |
                    +-- A has no BeanDefinition yet
                         because ConditionForA has not returned
~~~

This is a circular dependency right at the **registration decision level**, not merely a constructor cycle between two singletons with existing definitions. You may hit `NoSuchBeanDefinitionException`, circular dependency errors, or wrong-order initialization; the actual exception type depends on code and configuration.

The proper design is for conditions to read only enough **metadata** to decide whether to register A, while B is injected after A has a definition. If a condition genuinely needs to check a bean type, use Boot's `@ConditionalOnBean`/`@ConditionalOnMissingBean` appropriately; those conditions are designed to inspect definition metadata by phase.

### Do Not Hack Around It with `@DependsOn`

`@DependsOn` controls the **instantiation** order of already defined beans; it does not make a condition that calls `getBean` valid. Fix the registration logic first rather than trying to force bean instance order.

## 13. Conditions on Classes, Methods, and Processing Phases

A condition applied on a **`@Configuration` class** can cause Spring to skip the entire configuration class and its related methods/imports/scans. A condition on a **`@Bean` method** targets that method's definition.

For conditions needing phase control, Spring Framework provides the `ConfigurationCondition` interface (extending `Condition`) with:

~~~java
ConfigurationPhase getConfigurationPhase();
~~~

The two distinguished phases are `PARSE_CONFIGURATION` and `REGISTER_BEAN`. That is why a condition needing metadata or bean definitions must understand **which phase** it runs in.

However, `ConfigurationCondition` does not legitimize fetching bean instances. Even when running in `REGISTER_BEAN`, the contract against interacting with bean instances remains in force. It only specifies when to evaluate the configuration condition, without guaranteeing all beans are already instantiated.

## 14. Common Mistakes and Consequences

| Mistake | Why it is dangerous | Solution |
| --- | --- | --- |
| `context.getBeanFactory().getBean(...)` in `matches` | Can instantiate objects before context is ready | Read metadata/registry or use specialized Boot conditions |
| `new DatabaseClient()` and connecting inside a condition | I/O, timeouts, missing lifecycle/disposal | Build the client under `@Bean` and manage init/close |
| HTTP request to external service to decide a condition | Transient state breaks config or slows startup | Feature flag + health/retry at runtime |
| Sending emails or publishing events in a condition | Can happen even if bean is blocked; no once-only guarantee | Runner/event/lifecycle with idempotency |
| Writing files/cache/DB inside a condition | Side effects are not rolled back if startup fails | Move to transactional tasks or application APIs |
| Counting invocations to drive `matches` | No guarantee a condition runs only once | Check stable data, do not rely on counters |
| Querying unprocessed bean definitions | Outcome depends on configuration order | Understand phases; use `@ConditionalOnBean`/`OnMissingBean` in proper context |
| Using SpEL bean references in `@ConditionalOnExpression` | Risks premature bean instantiation | Use `@ConditionalOnProperty`/`@ConditionalOnClass` where appropriate |
| Using conditions for live runtime toggling | Conditions do not re-evaluate automatically when properties change | Runtime config, controlled refresh, or business logic |
| Throwing/swallowing unexpected exceptions inconsistently | Unreadable startup failures or hidden config bugs | Simple conditions, clear configuration validation |

## 15. How to Test Conditions Safely

### Verify Registration Outcomes, Do Not Measure Call Counts

In a demo application, perform independent runs with varying properties and check:

1. Presence or absence of the corresponding `BeanDefinition`.
2. Whether the bean instance is created when requested by the container.
3. Whether expected business side effects appear only in the appropriate lifecycle.
4. Startup time and logs show no timeouts or premature resource initialization.

Do not insert a counter into `matches` and assert it equals one. That is not a contract Spring guarantees, and it makes tests brittle.

### With Spring Boot: `ApplicationContextRunner`

Spring Boot test provides `ApplicationContextRunner` to create isolated contexts with varying properties and user configurations, especially suited for auto-configuration. Conceptual example:

~~~java
// TEST ILLUSTRATION SNIPPET: requires spring-boot-test dependency
// and assertion library, not a standalone program.
new ApplicationContextRunner()
    .withUserConfiguration(FeatureConfiguration.class)
    .withPropertyValues("demo.feature.enabled=false")
    .run(context -> {
        assertThat(context).doesNotHaveBean(CountedService.class);
    });
~~~

*This snippet requires imports and AssertJ in a test project; not code to paste into `main`.* Tests should assert **bean presence/absence**, rather than assuming a condition runs a specific number of times. A real auto-configuration can also be tested across pairs of classpath/property/user-bean conditions to catch ordering bugs.

### Read the Condition Evaluation Report Within Its Scope

Spring Boot provides the Condition Evaluation Report (viewable with `--debug`) to explain many Spring Boot conditions and match/no-match reasons. However, a plain custom `Condition` implementing only the Framework interface **is not necessarily reported the way `SpringBootCondition` builds `ConditionOutcome`**. When observing, inspect both the context and the report; do not conclude a condition did not run just because it has no dedicated line in the report.

### Errors Often Appear Before `main` Observes Anything

If a buggy condition calls `getBean` and throws an exception during context refresh, `SpringApplication.run(...)` can fail **before code after `run` executes**. In that case there is no expected bean-check output. Read the root stack trace instead of blaming `System.out.println` or provider lookup.

## 16. Self-Check Exercises

1. **Contract:** Why does `matches=true` not mean a singleton bean instance is already instantiated? Use `BeanDefinition` and `@Lazy` to explain.
2. **Analyzing the anti-pattern:** When a condition calls `getBean("remoteClient")`, what are at least four risks that can occur? Which belong to lifecycle, and which belong to registration order?
3. **Right timing:** If you need to send a message after startup, do you choose `ApplicationRunner` or `Condition.matches`? And for an exactly-once requirement across multiple instances, what else is needed?
4. **External service down:** Why can pinging an endpoint in a condition turn a temporary network blip into a configuration missing beans? Which layer should the check move to?
5. **Runnable code:** Run the section 9 project with property omitted, `true`, and `false`. Explain all four output lines, especially why `constructedBeforeLookup=0` yet `definition=true`.
6. **Try eager:** Remove `@Lazy`, rebuild, and predict the counter change. Did the condition itself create the instance?
7. **Try dependency:** Add an eager singleton bean depending on `CountedService`. Why does `@Lazy` no longer guarantee the constructor has not run before `main`?
8. **Ordering:** Distinguish `context.getRegistry().containsBeanDefinition("x")` from `context.getBeanFactory().getBean("x")`. Which operation can cause an instance to be created?
9. **Auto-configuration:** Why must `@ConditionalOnMissingBean` still account for definition registration order? Where does Boot recommend placing this condition primarily?
10. **SpEL:** Why can `@ConditionalOnExpression("@bean.check()")` be riskier than `@ConditionalOnProperty` at startup?
11. **Testing:** Why is asserting the invocation count of `matches` a brittle test design? What context state should you assert instead?
12. **Scope:** Why is `ConfigurationCondition.REGISTER_BEAN` not synonymous with "all bean instances are ready"?

**Completion criteria:** you can accurately explain the timing and role of `Condition.matches`, point out hazards of premature bean instantiation and side effects, write conditions that read only metadata/properties, verify the difference between registering a definition and creating an instance, and place business tasks in the proper lifecycle.

## 17. Official Documentation

- [Spring Framework 6.1 — `Condition` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Condition.html)
- [Spring Framework 6.1 — `ConditionContext` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConditionContext.html)
- [Spring Framework 6.1 — `ConfigurationCondition` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConfigurationCondition.html)
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 — Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html)
- [Spring Boot 3.3 — Application Startup / SpringApplication](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
