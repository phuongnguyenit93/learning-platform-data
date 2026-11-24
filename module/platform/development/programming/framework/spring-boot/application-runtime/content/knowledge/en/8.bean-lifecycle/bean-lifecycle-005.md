# SmartInitializingSingleton After Non-Lazy Singleton Creation

**Topic:** Spring Boot Application Runtime → Bean Lifecycle. This lesson explains the exact role of `SmartInitializingSingleton`, the `afterSingletonsInstantiated()` method, when Spring invokes the callback after finishing pre-instantiation of regular singletons, and the cases where the callback is **not** called. It includes a runnable Spring Boot application, a contrast with a lazy bean, a startup failure example, and verification criteria via logs/HTTP.

**Example platform:** Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x, and Spring MVC. In applications using other versions, read the corresponding Javadoc to confirm packages, contracts, and startup ordering. `SmartInitializingSingleton` is a **Spring Framework** interface, not a Spring Boot annotation.

## 1. When do you need SmartInitializingSingleton?

In an `ApplicationContext`, Spring holds **bean definitions** describing how beans are created. During refresh, the container normally pre-instantiates **non-lazy singletons**: creating objects, resolving dependencies, calling initialization callbacks, and applying `BeanPostProcessor`s. Sometimes a bean needs to do work **after this entire group of regular singletons has finished creation**, such as building a registry from other beans.

If you do that inside a constructor or `@PostConstruct`, you can run into issues: other singletons may not be created yet, and probing beans with `getBeansOfType(...)` can trigger unintended early instantiation. `SmartInitializingSingleton` provides a clearer milestone:

~~~java
package org.springframework.beans.factory;

public interface SmartInitializingSingleton {
    void afterSingletonsInstantiated();
}
~~~

When your singleton bean implements this interface and is created during pre-instantiation, the BeanFactory invokes `afterSingletonsInstantiated()` at the **end of that phase**. At that milestone, **regular singleton beans** under the pre-instantiation contract have already been created; looking up those singletons is safer than doing so while a single bean is still being initialized.

Correct takeaways to remember:

- **True:** the callback runs **after** regular, non-lazy singletons are initialized during BeanFactory bootstrap.
- **False:** the callback guarantees all beans of every scope have been created.
- **False:** the callback only runs after the HTTP server accepts requests or after `ApplicationReadyEvent`.
- **False:** a `@Lazy` singleton bean created on demand after startup also receives this callback automatically.
- **False:** implementing the interface means Spring manages a background task or shuts that task down automatically.

The Spring Framework Javadoc describes this interface as a callback **at the end of the singleton pre-instantiation phase** and recommends using `Lifecycle` if the goal is to start/stop asynchronous tasks.

## 2. Placing the callback in the lifecycle diagram

Consider a Spring Boot application starting normally:

~~~text
SpringApplication.run(args)
   |
   +-- create/prepare ApplicationContext and Environment
   +-- register bean definitions
   +-- refresh ApplicationContext
   |    |
   |    +-- BeanFactoryPostProcessors process metadata
   |    +-- register BeanPostProcessors
   |    +-- preInstantiateSingletons() during BeanFactory completion
   |    |    |
   |    |    +-- initialize non-lazy singletons
   |    |    |     constructor/factory method
   |    |    |     dependency injection
   |    |    |     @PostConstruct, afterPropertiesSet, custom init
   |    |    |     post-init BeanPostProcessor/proxy if any
   |    |    |
   |    |    +-- after creation loop: SmartInitializingSingleton
   |    |          afterSingletonsInstantiated()
   |    |
   |    +-- finish refresh, lifecycle processor
   |    +-- ContextRefreshedEvent
   |
   +-- ApplicationStartedEvent
   +-- ApplicationRunner / CommandLineRunner
   +-- ApplicationReadyEvent
   v
Application in running state
   |
   +-- later may create additional lazy/prototype/request-scoped beans
~~~

`DefaultListableBeanFactory.preInstantiateSingletons()` is the directly relevant phase. The `afterSingletonsInstantiated()` milestone belongs to the end of pre-instantiation, called inside `finishBeanFactoryInitialization(...)` of `AbstractApplicationContext.refresh()`. It happens **before** `ContextRefreshedEvent` and before Spring Boot's started/ready events during normal startup.

Note: this is a conceptual sequence. Spring may create certain infrastructure beans earlier and creates beans according to the dependency graph; do not assume beans are always initialized in class-name order or component-scan order. In Spring Framework 6.2, some beans configured for background bootstrap can also be initialized under separate concurrency mechanics, though non-lazy singletons still generally complete during the bootstrap phase before the post-pre-instantiation callback.

## 3. Comparison with other callbacks

| Mechanism | Primary timing | Useful guarantee | Not guaranteed |
|---|---|---|---|
| Constructor or factory method | When creating **that specific bean** | New object exists and constructor dependencies are resolved | Other beans have finished init |
| `@PostConstruct` | When that bean initializes after injection | Can prepare the bean's internal state | All singletons have been created |
| `InitializingBean.afterPropertiesSet()` | End of that bean's initialization | Required property injection is complete | ApplicationContext has refreshed |
| `SmartInitializingSingleton.afterSingletonsInstantiated()` | End of singleton pre-instantiation | Regular singletons have been created | Lazy/prototype/request beans created or app ready |
| `ContextRefreshedEvent` | When context finishes refresh | That specific context has refreshed | Boot runners have finished |
| `ApplicationRunner` / `CommandLineRunner` | After refresh, before ready | Runs application-level logic before the ready milestone | Safe mutation of beans already used during startup |
| `ApplicationReadyEvent` | After runners | Boot has reached the ready milestone | Every business endpoint is always healthy |
| `SmartLifecycle` | Startup/shutdown managed by LifecycleProcessor, with phases | Manages start/stop of operational tasks and dependencies | Equivalent to just a registry-building callback |

**Choose `SmartInitializingSingleton` when:** you need to build a registry, lookup table, or validate relationships among **eager singletons** after they have initialized. For a long-running task, background connection, or scheduler needing clean shutdown, consider `SmartLifecycle`; for application-level workflows before signaling readiness, use runners and a readiness policy.

## 4. Which bean models actually receive the callback?

Spring creates non-lazy singletons eagerly during refresh by default. However, `scope` and `lazy-init` alter the contract:

| Bean kind | Created in pre-instantiation? | `afterSingletonsInstantiated()`? |
|---|---|---|
| Non-lazy singleton implementing the interface | Usually yes | Yes, at the end of pre-instantiation |
| Non-lazy singleton not implementing the interface | Usually yes | No method to call |
| `@Lazy` singleton created only **after** bootstrap | No | Not called upon late creation |
| `@Lazy` singleton forced early by an eager dependency | May be created before the callback pass | Depends on whether it was already created during bootstrap; do not treat lazy as an absolute boundary |
| Prototype implementing the interface | Created per request | Does not belong to singleton pre-instantiation callback |
| Request/session-scoped bean | Follows respective web scope lifecycle | Does not belong to pre-instantiation callback |
| Bean absent because `@Conditional...` did not match | No matching definition | No |
| Singleton created on demand **after** bootstrap | Not pre-instantiated | No extra callback pass for late creation |

The phrase **“non-lazy”** in the title means **non-lazy/eager** singletons; it must not be misunderstood as “every singleton in the entire application” regardless of timing. `BeanFactory` can hold a lazy bean definition without an instance yet. In Spring Boot, `spring.main.lazy-initialization=true` changes pre-instantiation of many beans; a `SmartInitializingSingleton` made lazy by this setting may not be called during bootstrap.

**Exception to analyze in practice:** a singleton marked `@Lazy` that is directly injected into an eager singleton may still have to be created early by Spring to satisfy the dependency; using `ObjectProvider` or an injection-point `@Lazy` is what properly defers instance retrieval until needed.

## 5. Runnable sample app: rule registry built after eager singletons

We create two `ReadyRule`s, a `RuleCatalog` implementing `SmartInitializingSingleton`, a lazy bean with the same callback interface to demonstrate the exception, and a controller returning HTTP data. Inside the catalog's callback, we collect the created rules and publish status for the controller.

### 5.1. Create the project

From **Spring Initializr**, select:

- Project: Maven; Java: 17; Spring Boot: 3.5.x.
- Group: `com.example`; Artifact: `smart-init-lab`; package: `com.example.smartinit`.
- Dependency: **Spring Web**.
- Packaging: Jar.

Keep the `pom.xml`, dependencies, and plugin versions generated by Initializr. Source structure:

~~~text
smart-init-lab/
  pom.xml
  mvnw
  mvnw.cmd
  src/main/java/com/example/smartinit/
    SmartInitApplication.java
    ReadyRule.java
    AlphaRule.java
    BetaRule.java
    RuleCatalog.java
    DeferredProbe.java
    StatusController.java
  src/main/resources/application.properties
~~~

Each `public` class is placed in a file with the matching name in the same package. Because this is a Spring Boot application with external dependencies, build with the Maven Wrapper; running `javac` on a single file without the Spring classpath will report missing packages.

### 5.2. Main class and Boot startup milestones

File `SmartInitApplication.java`:

~~~java
package com.example.smartinit;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class SmartInitApplication {

    public static void main(String[] args) {
        SpringApplication.run(SmartInitApplication.class, args);
    }

    @Bean
    ApplicationRunner markerRunner(RuleCatalog catalog) {
        return args -> System.out.println(
                "LAB_RUNNER_READY=" + catalog.initialized());
    }

    @EventListener(ContextRefreshedEvent.class)
    public void contextRefreshed() {
        System.out.println("LAB_CONTEXT_REFRESHED");
    }

    @EventListener(ApplicationStartedEvent.class)
    public void applicationStarted() {
        System.out.println("LAB_APPLICATION_STARTED");
    }

    @EventListener(ApplicationReadyEvent.class)
    public void applicationReady() {
        System.out.println("LAB_APPLICATION_READY");
    }
}
~~~

`ApplicationRunner` receives `RuleCatalog` as a dependency to print observable status. During normal startup, the `SmartInitializingSingleton` callback must complete **before** the runner executes. `ContextRefreshedEvent` proves context refresh completed; `ApplicationStartedEvent` arrives after refresh but before runners; `ApplicationReadyEvent` comes after runners.

### 5.3. Interface and two eager beans

File `ReadyRule.java`:

~~~java
package com.example.smartinit;

public interface ReadyRule {
    String code();
}
~~~

File `AlphaRule.java`:

~~~java
package com.example.smartinit;

import org.springframework.stereotype.Component;

@Component
public final class AlphaRule implements ReadyRule {

    public AlphaRule() {
        System.out.println("LAB_ALPHA_CONSTRUCTED");
    }

    @Override
    public String code() {
        return "alpha";
    }
}
~~~

File `BetaRule.java`:

~~~java
package com.example.smartinit;

import org.springframework.stereotype.Component;

@Component
public final class BetaRule implements ReadyRule {

    public BetaRule() {
        System.out.println("LAB_BETA_CONSTRUCTED");
    }

    @Override
    public String code() {
        return "beta";
    }
}
~~~

Both classes are singletons by default scope and have no `@Lazy`. Thus in this simple example, Spring creates them during refresh. Do **not** assume Alpha is always created before Beta: ordering between two beans with no dependency between them should only be checked with markers, not relied upon as a business contract.

### 5.4. RuleCatalog: callback after eager singletons have been created

File `RuleCatalog.java`:

~~~java
package com.example.smartinit;

import java.util.List;
import java.util.Map;
import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.ListableBeanFactory;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public final class RuleCatalog implements SmartInitializingSingleton {

    private final ListableBeanFactory beanFactory;
    private final boolean failOnSmart;
    private volatile List<String> codes = List.of();

    public RuleCatalog(
            ListableBeanFactory beanFactory,
            @Value("${lab.fail-on-smart:false}") boolean failOnSmart) {
        this.beanFactory = beanFactory;
        this.failOnSmart = failOnSmart;
        System.out.println("LAB_CATALOG_CONSTRUCTED");
    }

    @PostConstruct
    public void init() {
        System.out.println("LAB_CATALOG_POST_CONSTRUCT");
    }

    @Override
    public void afterSingletonsInstantiated() {
        Map<String, ReadyRule> beans =
                beanFactory.getBeansOfType(ReadyRule.class);

        List<String> discovered = beans.values()
                .stream()
                .map(ReadyRule::code)
                .sorted()
                .toList();

        if (discovered.size() != 2) {
            throw new IllegalStateException(
                    "LAB_RULE_COUNT_INVALID: " + discovered.size());
        }
        if (failOnSmart) {
            System.out.println("LAB_SMART_FAILURE_TRIGGERED");
            throw new IllegalStateException("LAB_SMART_INIT_FAILED");
        }

        this.codes = List.copyOf(discovered);
        System.out.println("LAB_SMART_DONE=" + String.join(",", codes));
    }

    public boolean initialized() {
        return !codes.isEmpty();
    }

    public List<String> codes() {
        return codes;
    }
}
~~~

**Mechanism explanation:**

1. `@Component` registers the `RuleCatalog` bean with Spring; merely implementing the interface without registering a bean will **not trigger** the callback automatically.
2. `@PostConstruct` is `RuleCatalog`'s **own** milestone, so it usually appears **before** `LAB_SMART_DONE`. It does not prove Alpha/Beta have been created.
3. `afterSingletonsInstantiated()` is called by Spring after the pre-instantiation loop. Inside it, `beanFactory.getBeansOfType(ReadyRule.class)` fetches the registered rules; per Javadoc, this timing helps avoid side effects from accidentally instantiating **regular singletons** too early.
4. We sort rule codes with `sorted()` so the result is deterministic without depending on component scan order or Map iteration order.
5. `volatile List<String> codes` publishes an immutable list after the callback; the application can read it afterward. For multi-step logic changing continuously, proper synchronization is needed rather than sprinkling `volatile` arbitrarily.
6. The `lab.fail-on-smart` parameter is solely for the failure experiment later; its default is `false`. When enabled, an exception thrown from the callback aborts startup before the context finishes refreshing.

In large applications, `getBeansOfType(...)` can still interact with definitions having special semantics such as lazy, `FactoryBean`, or scoped proxies. The Javadoc guarantees the suitability of the post-singleton-pre-instantiation milestone, **not** carte blanche to scan and instantiate every bean outside your scope. Restrict the target type you query, understand scopes, and avoid lookup calls with unexpected state-changing side effects.

### 5.5. Contrast: lazy bean implementing the interface without receiving a late callback

File `DeferredProbe.java`:

~~~java
package com.example.smartinit;

import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.context.annotation.Lazy;
import org.springframework.stereotype.Component;

@Component
@Lazy
public final class DeferredProbe implements SmartInitializingSingleton {

    public DeferredProbe() {
        System.out.println("LAB_DEFERRED_CONSTRUCTED");
    }

    public String message() {
        return "created-on-demand";
    }

    @Override
    public void afterSingletonsInstantiated() {
        System.out.println("LAB_DEFERRED_SMART_CALLBACK");
    }
}
~~~

This bean is marked `@Lazy` and is only retrieved by the controller via `ObjectProvider` when a special request is made. As long as no other eager bean forces `DeferredProbe` to be created, `afterSingletonsInstantiated()` does **not** run during refresh because the bean does not exist yet. When the bean is created on demand after refresh, Spring also **does not retroactively run** this callback. This is a core difference from `@PostConstruct` or `InitializingBean`, which are tied to the creation of that bean itself.

### 5.6. Controller for independent HTTP evidence

File `StatusController.java`:

~~~java
package com.example.smartinit;

import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StatusController {

    private final RuleCatalog catalog;
    private final ObjectProvider<DeferredProbe> deferred;

    public StatusController(
            RuleCatalog catalog,
            ObjectProvider<DeferredProbe> deferred) {
        this.catalog = catalog;
        this.deferred = deferred;
    }

    @GetMapping("/status")
    public CatalogStatus status() {
        return new CatalogStatus(
                catalog.initialized(),
                catalog.codes());
    }

    @GetMapping("/deferred")
    public Map<String, String> deferred() {
        return Map.of("result", deferred.getObject().message());
    }

    public record CatalogStatus(boolean initialized, List<String> rules) {
    }
}
~~~

`/status` checks the result published by the callback; `/deferred` requests the lazy bean for the first time. `ObjectProvider<DeferredProbe>` prevents the controller from having to instantiate `DeferredProbe` inside the controller's own constructor. `CatalogStatus` is a Java record serialized to JSON by Spring Web/Jackson.

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=smart-init-lab
server.port=8080
lab.fail-on-smart=false
~~~

**Do not invoke the callback manually.** Spring's BeanFactory recognizes the interface on singleton beans and coordinates it at the proper moment.

## 6. Running the lab and proving the actual order

### 6.1. Maven Wrapper

Inside the `smart-init-lab` directory, on Linux/macOS:

~~~bash
java -version
./mvnw -version
./mvnw spring-boot:run
~~~

On Windows PowerShell:

~~~powershell
java -version
./mvnw.cmd -version
./mvnw.cmd spring-boot:run
~~~

JDK and compiler must satisfy Java 17. On Windows if `curl` is a PowerShell alias, use `curl.exe` for the examples below.

### 6.2. Markers to observe

In successful output, the markers have these key ordering relationships:

~~~text
LAB_ALPHA_CONSTRUCTED
LAB_BETA_CONSTRUCTED
LAB_CATALOG_CONSTRUCTED
LAB_CATALOG_POST_CONSTRUCT
LAB_SMART_DONE=alpha,beta
LAB_CONTEXT_REFRESHED
LAB_APPLICATION_STARTED
LAB_RUNNER_READY=true
LAB_APPLICATION_READY
~~~

**This is one valid illustrative sequence, not a line-for-line guaranteed log.** The two rules and the catalog can appear in different orders before the callback because the dependency graph and bean creation order determine them. What you must verify is that **all rule construction and catalog init markers appear before `LAB_SMART_DONE`**, followed by refreshed/started/runner/ready. Timestamps, PID, Tomcat messages, and other log lines will also vary.

In the default run, `LAB_DEFERRED_CONSTRUCTED` does not appear yet; `LAB_DEFERRED_SMART_CALLBACK` does not appear either.

### 6.3. Reading HTTP responses

Open another terminal while the server is on port 8080:

~~~bash
curl -i "http://localhost:8080/status"
~~~

Expect HTTP 200 and JSON equivalent to:

~~~json
{"initialized":true,"rules":["alpha","beta"]}
~~~

Additional headers and JSON property ordering may vary by serializer. In the example, the body proves the callback built the catalog before requests are served after ready. Do **not** infer from this body that all external system dependencies are healthy; the sample app contains only internal rules.

Continue:

~~~bash
curl -i "http://localhost:8080/deferred"
curl -i "http://localhost:8080/deferred"
~~~

Both calls are expected to return HTTP 200 and:

~~~json
{"result":"created-on-demand"}
~~~

After the first request, the console shows:

~~~text
LAB_DEFERRED_CONSTRUCTED
~~~

But **there is no**:

~~~text
LAB_DEFERRED_SMART_CALLBACK
~~~

The absence of the callback is the correct result per contract: `SmartInitializingSingleton` is only scanned/invoked at the end of pre-instantiation, not replayed whenever a lazy singleton is created late. If a lazy bean needs init logic **when it itself is created**, use `@PostConstruct` or another suitable init mechanism, not this callback.

### 6.4. Running via packaged JAR

Stop the Maven session listening on the port, then run:

~~~bash
./mvnw clean package
java -jar target/smart-init-lab-0.0.1-SNAPSHOT.jar
~~~

On Windows use `./mvnw.cmd clean package` to build. If the artifact version differs from `0.0.1-SNAPSHOT`, use the actual JAR name in `target/` rather than the illustrative name. Once the JAR is running, call `/status` and `/deferred` again and compare the markers. Do not run two instances simultaneously on the same port.

## 7. Why is getBeansOfType(...) safer here than in PostConstruct?

Imagine `RuleCatalog` wanting to find all `ReadyRule` beans via:

~~~java
beanFactory.getBeansOfType(ReadyRule.class);
~~~

If called from `RuleCatalog.@PostConstruct`, the container may still be creating other singletons. A “find every bean of this type” query at that point can pull in early instantiations, alter the initialization timing graph, or expose beans to components that are not ready yet.

In `afterSingletonsInstantiated()`, Spring has finished pre-instantiation of **regular singletons**, so the required objects in that group already exist. Hence it is a good place to build plugin → bean mappings, handler → strategy tables, or collect metadata from singletons. Still:

- If you want to iterate over **a fixed set of services**, constructor injection of `List<ReadyRule>` may be simpler and more type-safe; the callback timing remains useful if assembly needs to wait for singletons to finish.
- Do not casually call `getBeansOfType(Object.class)` across the entire BeanFactory and expect everything to be safe; many bean types and factories have special semantics.
- Do not assume `getBeansOfType` returns only non-lazy beans when default lookup walks special definitions too; understand lookup policies and design target interfaces specifically enough.
- Do not rely on the returned Map's order if business results need deterministic ordering; use `@Order`/`Ordered` or sort keys explicitly.
- Some beans may be proxies: if you call an interface method to read metadata, that method may be advised; avoid placing I/O and uncontrolled side effects into catalog building.

A plugin system sometimes uses a Spring-injected `Map<String, Handler>` directly rather than querying the BeanFactory. When there is no requirement for the post-pre-instantiation milestone, do not add `SmartInitializingSingleton` merely because you have multiple handlers.

## 8. Comparing @PostConstruct, InitializingBean, and SmartInitializingSingleton

A singleton can implement both `InitializingBean` and `SmartInitializingSingleton`:

~~~java
@Component
class ExampleBean implements InitializingBean, SmartInitializingSingleton {

    @PostConstruct
    void postConstruct() {
        System.out.println("POST_CONSTRUCT");
    }

    @Override
    public void afterPropertiesSet() {
        System.out.println("AFTER_PROPERTIES_SET");
    }

    @Override
    public void afterSingletonsInstantiated() {
        System.out.println("AFTER_ALL_REGULAR_SINGLETONS");
    }
}
~~~

**This is a snippet to place inside a project with Spring imports and appropriate classes**, not a standalone complete `ExampleBean.java` file. Typical order for an eager bean:

~~~text
POST_CONSTRUCT
AFTER_PROPERTIES_SET
AFTER_ALL_REGULAR_SINGLETONS
~~~

`@PostConstruct` is invoked by the relevant post-processor during the bean's init step; `InitializingBean.afterPropertiesSet()` is called during **that bean's** initialization step; `SmartInitializingSingleton` runs after pre-instantiation of **the entire set of regular singletons**. If this bean is lazily created after bootstrap, the first two callbacks can still run at creation time, while the last callback will not be retroactively called.

Distinguish `SmartInitializingSingleton` from `SmartLifecycle`: both names start with “Smart”, yet their goals differ. `SmartLifecycle` has running state, `start()`, `stop()`, phases, and auto-startup, making it suitable for long-lived consumers/tasks with start/stop; this callback is merely a one-time **registry/singleton initialization** milestone during bootstrap.

## 9. Distinguishing the callback from ContextRefreshedEvent

Both approaches can be used for logic “after many beans exist”, but their contracts differ:

### SmartInitializingSingleton

- Belongs to the `spring-beans` module, requiring no `ApplicationContext` with an event publisher.
- Can be invoked by an appropriate `ListableBeanFactory` executing `preInstantiateSingletons()`.
- Tied to **singleton pre-instantiation**, not refresh events.
- Needs no filtering of context hierarchy or checking whether an event came from a child context.
- Does not re-run just because a listener receives another `ContextRefreshedEvent` or a new lazy bean is created.

### ContextRefreshedEvent

- Belongs to the `ApplicationContext` event system.
- Published after the context finishes refreshing.
- With a parent/child hierarchy, child context events can propagate to the parent context; listeners targeting a specific context must filter by `event.getApplicationContext()`.
- Some contexts support multiple refreshes or recreated contexts, so the event may fire multiple times across the overall lifecycle.
- Appropriate when reacting at the context-refreshed level and event architecture, rather than just BeanFactory pre-instantiation.

**Selection rule:** if you want a bean-level callback at the end of pre-instantiation, choose `SmartInitializingSingleton`. If you want to observe a refreshed context with explicit event handling, consider `ContextRefreshedEvent`. If you want to execute application-level work after refresh but before ready, use `ApplicationRunner` or `CommandLineRunner`.

## 10. Experiment 1 — Throwing an exception from the callback

`RuleCatalog`'s code already has the `lab.fail-on-smart` branch. Stop any instance running on port 8080, ensure the JAR is built, and run:

~~~bash
java -jar target/smart-init-lab-0.0.1-SNAPSHOT.jar --lab.fail-on-smart=true
~~~

When Spring calls `afterSingletonsInstantiated()`, the failure branch prints:

~~~text
LAB_SMART_FAILURE_TRIGGERED
~~~

Then it throws `IllegalStateException` with message `LAB_SMART_INIT_FAILED`. Expected outcomes:

1. The stack trace reports a cause related to `LAB_SMART_INIT_FAILED`; outer wrapper exception classes vary by stack.
2. Bean constructors and init callbacks of many singletons may already have run.
3. **No** `LAB_SMART_DONE=alpha,beta` because the callback did not complete.
4. **No** `LAB_CONTEXT_REFRESHED`, `LAB_APPLICATION_STARTED`, `LAB_RUNNER_READY=true`, or `LAB_APPLICATION_READY` markers for the failed startup.
5. Spring Boot terminates startup with an error; the application is not considered ready. Some web infrastructure may already have initialized beforehand, though Spring will attempt cleanup while aborting startup.

This is a **startup failure occurring inside pre-instantiation**, unlike an error when a controller handles a request. If the callback performs mandatory configuration validation, throwing an exception may be the right policy to prevent the app from serving in an invalid state. If the failure is transient and work should retry, design proper retries/timeouts and readiness handling; do not spin in an infinite loop inside the callback.

Run again without passing the error flag or use `--lab.fail-on-smart=false` to confirm startup returns to normal.

## 11. Experiment 2 — Switching global lazy initialization

In a separate run, try:

~~~bash
java -jar target/smart-init-lab-0.0.1-SNAPSHOT.jar --spring.main.lazy-initialization=true
~~~

Do not force an exact fixed marker count, because which beans infrastructure still needs early depends on configuration and version. The key principle, however, is that a bean implementing `SmartInitializingSingleton` is only called in the callback sweep if it already exists during pre-instantiation. Beans deferred by global lazy mode may **not receive the callback**.

In this project, `ApplicationRunner` requires `RuleCatalog`, so the framework may have to instantiate the catalog when finding and running runners **after refresh** under global lazy mode. In that case the catalog runs its constructor and `@PostConstruct`, yet the post-pre-instantiation pass has already passed; the runner may print:

~~~text
LAB_RUNNER_READY=false
~~~

and `/status` may return `initialized=false` with an empty array, because nothing retroactively invokes the callback. This example helps show how global lazy mode can break a design relying on eager callbacks. Actual results should be checked against the markers in your exact application and version.

If the catalog is **mandatory** and must be built before ready, ensure the bean and required dependencies are bootstrapped at the right time, or move the logic to a lifecycle phase with a clearer contract under global lazy mode (for example, a runner coordinating explicit initialization with controlled ordering). Do not manually call `afterSingletonsInstantiated()` arbitrarily to “patch” lazy mode, as that turns a container callback into a business method vulnerable to duplicate calls.

## 12. Experiment 3 — Prototype and request scope

`SmartInitializingSingleton` does not mean “every bean right after it is created”. To test this, in a **copy of the lab**, add a prototype bean snippet:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class PrototypeProbe implements SmartInitializingSingleton {

    public PrototypeProbe() {
        System.out.println("LAB_PROTOTYPE_CONSTRUCTED");
    }

    @Override
    public void afterSingletonsInstantiated() {
        System.out.println("LAB_PROTOTYPE_SMART");
    }
}
~~~

This snippet requires importing `org.springframework.context.annotation.Scope`, `org.springframework.beans.factory.config.ConfigurableBeanFactory`, `org.springframework.stereotype.Component`, and `org.springframework.beans.factory.SmartInitializingSingleton`. Place it in a separate class/file inside the scanned package. If you fetch the prototype bean via `ObjectProvider<PrototypeProbe>.getObject()`, the constructor runs on each new creation, yet `LAB_PROTOTYPE_SMART` is not called by the BeanFactory in the pre-instantiation callback sweep.

With `@RequestScope`, each request can receive a separate instance; it likewise does not belong to the post-eager-singleton sweep. Callbacks tied to the bean's own lifecycle such as `@PostConstruct` fit per-scope instances better, and cleanup must follow the specific scope's contract.

Do not confuse a singleton **accessed for the first time after startup** with a prototype: a lazy singleton still typically produces only one instance in the context, yet its `SmartInitializingSingleton` receives no late callback.

## 13. Practical design pattern: Registry of multiple singleton strategies

A sound use case for this callback is a system with multiple eager strategies that needs a lookup table built once, avoiding ad-hoc initialization inside bean constructors:

~~~java
@Override
public void afterSingletonsInstantiated() {
    Map<String, MyStrategy> beans =
            beanFactory.getBeansOfType(MyStrategy.class);

    Map<String, MyStrategy> byCode = new HashMap<>();
    for (MyStrategy strategy : beans.values()) {
        MyStrategy old = byCode.putIfAbsent(strategy.code(), strategy);
        if (old != null) {
            throw new IllegalStateException(
                    "Duplicate strategy code: " + strategy.code());
        }
    }
    this.registry = Map.copyOf(byCode);
}
~~~

This is an **illustrative method snippet** placed in a class that already has `beanFactory`, `registry`, and the corresponding imports; it is not a standalone program. Good design practices:

- Narrow the bean type queried to avoid triggering unintended side effects.
- Ensure the registry is immutable after publication, or synchronize explicitly if runtime updates are needed.
- Check duplicate strategy codes during startup so errors surface early.
- Do not retain prototype/request-scoped beans as long-lived shared singletons.
- When there is no requirement for “after all singletons”, constructor injection of `List<MyStrategy>` is often cleaner.
- If a strategy depends on a data source, message broker, or external I/O, manage readiness/retry/timeout separately. This callback does not replace a health check.

**Deployment reliability:** if an application relies on this callback to build critical state, test it under lazy settings, conditional beans, parent/child contexts, and startup failures. Do not rely on a self-set boolean flag without real business verification.

## 14. Startup time, asynchronous work, and thread safety

`afterSingletonsInstantiated()` normally runs synchronously on the bootstrap thread. Long-running work here prolongs `ApplicationContext.refresh()` and can block the ready milestone. Lightweight CPU tasks such as building lookup tables, validating internal schemas, and checking duplicate keys are usually suitable; unbounded network queries, long sleeps, or infinite polling are not.

If you need to launch background tasks, Spring documentation recommends `Lifecycle`/`SmartLifecycle` to manage both starting and stopping. A background consumer must be stopped when the context closes; a single callback interface has no `stop()`. If readiness state needs to reflect dependency availability, design proper readiness checks rather than just printing “initialized”.

Data read by multiple HTTP threads can be stored in an immutable collection, a `final` field constructed in the constructor, or published via `volatile`/atomic references if assembled after construction. In the example, `codes` is `volatile` and assigned an immutable list after the callback; that suffices to demonstrate reference visibility. Do not infer that a multi-field sequence of operations becomes atomic solely from one volatile variable.

If the callback throws an exception, other beans may already have executed init side effects. Spring attempts to clean up the context, yet does not guarantee rolling back every operation against files, databases, or external systems. Initialization tasks should be idempotent whenever the application may restart multiple times.

## 15. Diagnosing common errors

| Symptom | Plausible hypothesis | How to check |
|---|---|---|
| `afterSingletonsInstantiated()` never seen | Class is not a Spring-managed bean; lazy bean; non-singleton; context did not finish bootstrap | Check `@Component`/`@Bean`, scope, lazy flag, and stack trace |
| Constructor ran but callback missing | Bean created after pre-instantiation, often due to lazy | Compare constructor marker timing against `ContextRefreshedEvent`; check who called `getBean` |
| Callback runs before another lazy bean | Can be completely normal | Check whether the lazy bean was required by an eager dependency |
| Callback sees unexpected rule count | `@Conditional`, component scan, profile, or missing/duplicate implementation | Print bean names for the exact interface; check conditions and scan packages |
| Saw `@PostConstruct` and assumed catalog finished | Two different milestones | Check `LAB_SMART_DONE` and HTTP `/status` |
| Startup error `LAB_SMART_INIT_FAILED` | Exception from callback during refresh | Read `Caused by`, `lab.fail-on-smart` flag, pre-ready state |
| App reports started but API returns wrong data | Not every business invariant is proven by an event | Inspect JSON, bean dependencies, request path |
| Global lazy enabled and callback does not run | Bean created after singleton bootstrap | Compare markers with runner; design eager or appropriate lifecycle handling |
| Used callback to start a thread that never stops | Interface has no shutdown contract | Switch to `SmartLifecycle` or manage resources with proper destroy callbacks |
| Parent/child context yields duplicate results | Each BeanFactory has its own pre-instantiation pass | Log context identity and determine which context owns the bean |
| Two beans implement callback with reversed log order | Do not rely on unspecified callback ordering for business logic | Express dependency/lifecycle ordering using explicit mechanisms |
| Bean created post-bootstrap and callback called manually | Risk of running logic twice or violating container invariants | Choose the right-timed hook instead of turning a callback into a public operation |
| Registry read by requests before construction finishes | Inappropriate startup/lazy policy or weak concurrency design | Verify readiness and immutable publication |

**Notable design pitfall:** using `SmartInitializingSingleton` as a “safer `@PostConstruct`” for every bean. That is wrong in both scope and timing. For late-created prototypes/lazy beans, the callback is not invoked; for eager singletons, the callback can be blocked if another bean fails before bootstrap completes.

## 16. Test matrix and acceptance criteria

Practice in the sequence below:

| Experiment | Input/trigger | Observation to record | Correct conclusion |
|---|---|---|---|
| Default | `./mvnw spring-boot:run` | Rule constructors and catalog init before `LAB_SMART_DONE` | Callback runs after eager singleton bootstrap |
| Startup events | Track markers | `LAB_SMART_DONE` before context refreshed and started/ready | Callback sits inside refresh |
| Working API | `GET /status` | 200, `initialized=true`, `alpha/beta` | Registry was built |
| Lazy bean | First `GET /deferred` | Lazy constructor appears post-startup; no smart callback | Callback does not run retroactively |
| Startup error | `--lab.fail-on-smart=true` | Exception marker, no ready | Callback failure aborts refresh |
| Global lazy | `--spring.main.lazy-initialization=true` | Catalog creation and callback timing may change | Do not rely on callback if bean is deferred |
| Prototype | Request a prototype bean implementing interface | Constructor runs, callback is not called | Non-singleton scopes are excluded from sweep |

For each test, record: JDK/Spring Boot version; command run; timestamped marker lines; HTTP status and body (if any); root exception; a brief explanation of why the callback did or did not run. Our custom log markers are **not** built-in framework logs.

### Self-check questions

**1. Why is `afterSingletonsInstantiated()` not equivalent to `@PostConstruct`?** Because `@PostConstruct` runs when **that bean itself** is initialized, whereas the Smart callback runs at the end of creating **regular singletons**.

**2. Should you write a `@Lazy` singleton service and expect the callback to run automatically on the first request?** No. A lazy bean created late will not have `afterSingletonsInstantiated()` invoked by the earlier sweep.

**3. An eager bean implements the interface, but another bean's startup fails before pre-instantiation completes—what happens?** There is no guarantee its callback was called. A failed startup cannot be treated as having reached this milestone.

**4. Does `ContextRefreshedEvent` occur before the callback?** Not in the standard refresh flow: the Smart sweep sits inside BeanFactory completion before `finishRefresh()` publishes the event.

**5. If you need to start/stop a background worker, is this interface enough?** No. You need `Lifecycle`/`SmartLifecycle` and a shutdown policy or equivalent to get a start/stop pair.

**6. Does `getBeansOfType(...)` inside the callback automatically guarantee it never instantiates any lazy bean?** No. The contract only gives a stable point after regular singleton pre-instantiation; lookups still require understanding bean scopes and special definition semantics.

**7. Why sort the rule codes in the example?** Because bean creation order and Map iteration order should not become business assumptions. `sorted()` gives deterministic JSON for comparison.

**8. Should you call `afterSingletonsInstantiated()` directly in a controller when the catalog is not ready?** No. Doing so bypasses container lifecycle and can repeat side effects; fix the initialization and readiness policy instead.

**9. Does `ApplicationRunner` run before or after the callback during normal startup?** After, because Boot runners execute after context refresh.

**10. Can the callback run in a BeanFactory without ApplicationContext events?** Yes, the interface belongs to `spring-beans` and is honored by `ListableBeanFactory` implementations performing appropriate bootstrap, independent of `ApplicationContext`'s event system.

## 17. Lesson completion checklist

- [ ] Explain that `SmartInitializingSingleton` belongs to Spring Framework and is called back at the end of singleton pre-instantiation.
- [ ] Point out the callback's location inside `finishBeanFactoryInitialization` and before `ContextRefreshedEvent`.
- [ ] Distinguish bean definitions, eager singletons, lazy singletons, prototypes, and request scope.
- [ ] Write a Spring bean implementing `SmartInitializingSingleton` and observe the callback running exactly once during successful bootstrap.
- [ ] Compare the order of `@PostConstruct`, the smart callback, context refreshed, runners, and ready.
- [ ] Build and run a Java 17 and Spring Boot 3.5.x project with Maven Wrapper.
- [ ] Call `GET /status` and verify the registry was built from two `ReadyRule`s.
- [ ] Call `GET /deferred` and prove lazy beans do not receive a late callback.
- [ ] Trigger a controlled failure inside the callback and analyze the startup failure.
- [ ] Describe the impact of global lazy initialization on the callback contract.
- [ ] Choose the right hook for internal init, registries, application-level work, and stoppable background tasks.
- [ ] State limitations regarding `getBeansOfType`, callback ordering, concurrency, and cleanup after failed startup.

## 18. Official documentation

- Spring Framework 6.2 — `SmartInitializingSingleton` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.3/javadoc-api/org/springframework/beans/factory/SmartInitializingSingleton.html
- Spring Framework 6.2 — `ConfigurableListableBeanFactory.preInstantiateSingletons()`: https://docs.spring.io/spring-framework/docs/6.2.3/javadoc-api/org/springframework/beans/factory/config/ConfigurableListableBeanFactory.html
- Spring Framework — Bean lifecycle callbacks: https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html
- Spring Framework — Lazy initialization: https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-lazy-init.html
- Spring Framework — Application startup steps (`spring.beans.smart-initialize`): https://docs.spring.io/spring-framework/reference/6.2/core/appendix/application-startup-steps.html
- Spring Boot 3.5 — Application events/runner: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html

The ultimate goal of this lesson is to have **reproducible evidence** for lifecycle boundaries: eager singletons are created before the callback, the callback completes before context refreshed, and lazy beans created post-bootstrap do not receive another pass of the Smart callback. Reading these boundaries accurately helps you design registry and service initialization code that stays reliable when application configuration changes.