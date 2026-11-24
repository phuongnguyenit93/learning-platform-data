# BeanNameAware, BeanFactoryAware, and ApplicationContextAware in Spring Framework

## 1. The Problem: A Bean Needs Information from the Container

Dependency Injection (DI) is the central principle of the Spring Core Container: a regular bean should **receive its required business dependencies through constructors, setters, or other injection mechanisms**, rather than looking everything up in the container itself. However, certain infrastructure beans need to know **what name the container registered them under**, **which `BeanFactory` manages them**, or **which `ApplicationContext` contains them**.

Spring provides `Aware`-style interfaces for that need. When a Spring-managed bean implements one of the corresponding interfaces, the container invokes the callback and passes the appropriate infrastructure information into the instance.

Three core interfaces:

- `BeanNameAware` — receives the **actual registered bean name** via `setBeanName(String name)`.
- `BeanFactoryAware` — receives the **BeanFactory owning the bean** via `setBeanFactory(BeanFactory beanFactory)`.
- `ApplicationContextAware` — receives the **ApplicationContext enclosing the bean** via `setApplicationContext(ApplicationContext applicationContext)`.

These callbacks take place **after regular property population** and **before init callbacks such as `InitializingBean.afterPropertiesSet()` and custom init methods**. They are a mechanism for the container to notify the bean of infrastructure, not a signal that "the entire application has finished starting up".

### Visual Model

~~~text
ApplicationContext (provides high-level APIs)
    │
    ├── BeanFactory (manages bean definitions and bean instances)
    │       │
    │       └── creates bean "auditAdapter"
    │                │
    │                ├── constructor / factory method
    │                ├── regular dependency/property injection
    │                ├── BeanNameAware.setBeanName("auditAdapter")
    │                ├── BeanFactoryAware.setBeanFactory(beanFactory)
    │                ├── ApplicationContextAware.setApplicationContext(context)
    │                ├── @PostConstruct and init callbacks
    │                └── bean finishes post-processing
    │
    └── the program can retrieve the initialized bean
~~~

This is the **common sequence in a typical `ApplicationContext`**; `ApplicationContextAware` is actually handled through a context `BeanPostProcessor`, whereas `BeanNameAware` and `BeanFactoryAware` are called directly by the `BeanFactory` during initialization. The diagram is not a contract for the placement of **every** custom `BeanPostProcessor`, nor does it replace the full lifecycle of certain specialized beans.

## 2. What Does the `Aware` Interface Mean?

`org.springframework.beans.factory.Aware` is a marker interface: by itself, it declares no methods to implement. Specific interfaces extend `Aware` and declare callbacks carrying the appropriate information.

~~~java
// Illustrates API signatures; not a standalone Java file.
public interface BeanNameAware extends Aware {
    void setBeanName(String name);
}

public interface BeanFactoryAware extends Aware {
    void setBeanFactory(BeanFactory beanFactory) throws BeansException;
}

public interface ApplicationContextAware extends Aware {
    void setApplicationContext(ApplicationContext applicationContext)
            throws BeansException;
}
~~~

The definitions above have imports/documentation omitted to focus on the signatures; the actual namespaces are `org.springframework.beans.factory.BeanNameAware`, `org.springframework.beans.factory.BeanFactoryAware`, and `org.springframework.context.ApplicationContextAware`, respectively.

**Key point:** implementing the empty `Aware` interface alone does **not** make Spring inject everything automatically. A bean must implement a **specific interface** supported by the container or a processor. Whether Spring invokes the callback depends on the bean **being managed by a suitable container**. Calling `new MyAwareBean()` directly outside Spring does not trigger these callbacks automatically.

### Quick Comparison Table

| Interface | Callback | Value Received | Commonly Used For |
| --- | --- | --- | --- |
| `BeanNameAware` | `setBeanName(String)` | Actual bean name in BeanFactory | Adapters, infrastructure needing bean name in metadata/logs |
| `BeanFactoryAware` | `setBeanFactory(BeanFactory)` | BeanFactory owning the bean | Infrastructure needing dependency lookup, factory metadata/lifecycle |
| `ApplicationContextAware` | `setApplicationContext(ApplicationContext)` | ApplicationContext of the bean | Infrastructure needing events, resources, messages, or context-level APIs |
| Regular constructor DI | Constructor invoked by Spring | Declared dependencies | Services, repositories, controllers, most business code |

All three Aware callbacks couple the object directly to Spring APIs. Use them only when **container information is genuinely needed**; when you only need `PaymentGateway`, inject `PaymentGateway`.

## 3. `BeanNameAware` — A Bean Learns Its Registered Name

### 3.1. How It Works

A class implements:

~~~java
import org.springframework.beans.factory.BeanNameAware;

public class NamedProcessor implements BeanNameAware {
    private String beanName;

    @Override
    public void setBeanName(String name) {
        this.beanName = name;
    }

    public String beanName() {
        return beanName;
    }
}
~~~

If registered under the name `namedProcessor`, Spring calls `setBeanName("namedProcessor")` during bean initialization.

~~~java
@Bean(name = "namedProcessor")
NamedProcessor namedProcessor() {
    return new NamedProcessor();
}
~~~

These two snippets can be placed in appropriate configuration files/classes; the code above illustrates a bean and a `@Bean` method, **not a complete Java program**.

### 3.2. Is the Bean Name the Class Name or Java Field Name?

No. A bean name is an **identifier inside the container**, depending on how it is registered:

- `@Bean` typically takes the method name when no other name is specified.
- `@Bean("shippingWorker")` explicitly sets the bean name to `shippingWorker`.
- Component scanning typically generates a name from the class name via `BeanNameGenerator`, though the rule can be customized.
- XML `<bean id="...">` specifies the id or aliases.
- Inner beans or beans registered programmatically via APIs may carry auto-generated names.

`BeanNameAware` receives the **actual bean name** managed by the factory. For some inner beans, Spring may adjust the name to keep it unique; therefore, the received name does not necessarily match a string in the original configuration 100%.

Example with aliases:

~~~java
@Bean(name = {"fastEncoder", "primaryEncoderAlias"})
Encoder encoder() {
    return new Encoder();
}
~~~

`BeanNameAware` is called with the primary bean name assigned to the definition by the container, **not called once per alias**. Do not rely on whichever alias a caller used during lookup to infer the callback value. Bean names can change when refactoring configuration; avoid building business logic around comparing fixed string names.

### 3.3. When Is It Useful?

- Logging infrastructure that needs to attach the bean name to diagnostic messages.
- An infrastructure adapter that must register resources under the exact bean name.
- A generic component sharing one class but registered as multiple bean definitions that needs to know the name of its **specific definition**.

Avoid using the bean name as a **user identifier key, order code, or security policy**; it is container metadata, not immutable business data.

## 4. `BeanFactoryAware` — Accessing the Factory Managing the Bean

### 4.1. Callback and Capabilities

`BeanFactoryAware` lets a bean receive a reference to the `org.springframework.beans.factory.BeanFactory` that actually owns it:

~~~java
import org.springframework.beans.BeansException;
import org.springframework.beans.factory.BeanFactory;
import org.springframework.beans.factory.BeanFactoryAware;

public class LookupAdapter implements BeanFactoryAware {
    private BeanFactory factory;

    @Override
    public void setBeanFactory(BeanFactory beanFactory) throws BeansException {
        this.factory = beanFactory;
    }

    public Encoder newEncoder() {
        return factory.getBean(Encoder.class);
    }
}
~~~

This is an illustrative snippet; the `Encoder` type requires a proper bean definition and matching imports/class. If the `Encoder` bean is a prototype, each `getBean(Encoder.class)` call makes the container perform a prototype-scoped lookup. If `Encoder` is a singleton, repeated lookups normally return the same instance.

The base `BeanFactory` interface provides operations such as `getBean(...)`, `containsBean(...)`, `isSingleton(...)`, `isPrototype(...)`, and `getType(...)`. It does **not mean** you are holding a `ConfigurableListableBeanFactory`: do not call definition-management APIs belonging only to extended interfaces when only a `BeanFactory` variable is declared.

### 4.2. How Does It Differ from Regular DI?

Direct injection:

~~~java
public ReportService(Encoder encoder) {
    this.encoder = encoder;
}
~~~

Advantages: the dependency is clearly visible in the constructor, easy to replace with a fake/mock in unit tests, and the bean does not depend on container lookups.

Calling `factory.getBean(Encoder.class)` yourself:

~~~java
public Encoder lookupEncoderWhenNeeded() {
    return factory.getBean(Encoder.class);
}
~~~

This has a specific advantage when you **genuinely need to obtain beans on demand and according to scope**. Drawbacks: the dependency is hidden inside a method; missing/ambiguous bean errors may surface at runtime; and the code is forced to know Spring and `BeanFactory`. For on-demand lookup, Spring generally recommends a more targeted approach such as `ObjectProvider<Encoder>` injected into the constructor.

Example:

~~~java
public ReportService(ObjectProvider<Encoder> encoders) {
    this.encoders = encoders;
}

public void execute() {
    Encoder instance = encoders.getObject();
    // Use instance for the required unit of work.
}
~~~

The snippets above are illustrative method/constructor samples, not a complete class. `ObjectProvider` resides in the `org.springframework.beans.factory` package. Having a provider **does not by itself guarantee a new instance**; the result depends on the scope of the bean resolved by the provider.

### 4.3. Why Shouldn't You Arbitrarily Call `getBean()` Directly Inside `setBeanFactory()`?

`setBeanFactory()` is called while **this very bean is still initializing**. Calling another bean there can force Spring to instantiate additional beans, cause circular dependencies, or pull in initialization side effects. If a mandatory dependency is needed, constructor injection is usually clearer. Do not use Aware callbacks as a startup orchestration mechanism.

Even though the Javadoc permits using `BeanFactory` inside the callback, that does not guarantee other beans have finished initializing or the entire application is ready.

## 5. `ApplicationContextAware` — Receiving the Spring Context

### 5.1. Callback

`ApplicationContextAware` gives a bean the current `org.springframework.context.ApplicationContext`:

~~~java
import org.springframework.beans.BeansException;
import org.springframework.context.ApplicationContext;
import org.springframework.context.ApplicationContextAware;

public class ContextInspector implements ApplicationContextAware {
    private ApplicationContext context;

    @Override
    public void setApplicationContext(ApplicationContext applicationContext)
            throws BeansException {
        this.context = applicationContext;
    }

    public boolean hasBean(String name) {
        return context.containsBean(name);
    }
}
~~~

This is an illustrative class. In an `ApplicationContext` such as `AnnotationConfigApplicationContext` or a web-aware context, Spring registers `ApplicationContextAwareProcessor` to supply the context before init callbacks.

### 5.2. What Does `ApplicationContext` Have Beyond `BeanFactory`?

`ApplicationContext` is a higher-level interface offering several additional features:

- Extends bean lookup capabilities from `ListableBeanFactory` and `HierarchicalBeanFactory`.
- `getResource(...)` to access resources as `Resource`.
- `getMessage(...)` via `MessageSource`, supporting i18n and resource bundles.
- `publishEvent(...)` via `ApplicationEventPublisher`.
- `getId()`, `getDisplayName()`, and `getParent()` to inspect metadata and context relationships.
- In management-capable variants such as `ConfigurableApplicationContext`, additional refresh/close/environment/lifecycle capabilities.

Do not interpret `ApplicationContextAware` as "permission to mutate any bean at any time". The supplied reference is the `ApplicationContext` interface, which should normally be used narrowly. Arbitrary casting to specific implementation classes reduces reusability and causes bugs across different contexts.

### 5.3. Prefer a Narrow Interface When Only One Capability Is Needed

If you only need to publish events, a narrower dependency is:

~~~java
public AuditService(ApplicationEventPublisher events) {
    this.events = events;
}
~~~

If you only need to read resources:

~~~java
public TemplateReader(ResourceLoader loader) {
    this.loader = loader;
}
~~~

If you only need i18n:

~~~java
public GreetingService(MessageSource messages) {
    this.messages = messages;
}
~~~

These are illustrative constructor snippets, assuming corresponding fields are declared and imports are present.

You can inject `ApplicationEventPublisher`, `ResourceLoader`, or `MessageSource`, or implement the specialized Aware interfaces (`ApplicationEventPublisherAware`, `ResourceLoaderAware`, `MessageSourceAware`) if writing infrastructure that requires callbacks. When you simply need a known collaborator, inject that collaborator directly.

### 5.4. Can a Bean Belong to Multiple ApplicationContexts?

An object created by a context normally receives the **context that owns or created it** via callback. An application may have a parent context and child contexts; they have separate bean registries and event semantics. Do not use a global static field to hold `ApplicationContext` and assume there is only one context for the entire JVM.

If two contexts register the same class as **two bean instances**, each instance can receive a different context. Attempting to reuse **the same raw object instance** under multiple bean definitions/contexts can cause callbacks to fire again and overwrite the reference; this is an unusual design to avoid when clear ownership is needed.

## 6. Invocation Order of the Three Aware Callbacks

In a standard `AnnotationConfigApplicationContext`, callbacks for the three core interfaces run in the following order:

1. `BeanNameAware.setBeanName(...)`, invoked directly by the `BeanFactory`.
2. `BeanFactoryAware.setBeanFactory(...)`, after `BeanClassLoaderAware` if present.
3. `ApplicationContextAware.setApplicationContext(...)`, performed by `ApplicationContextAwareProcessor` during the `BeanPostProcessor.before` phase.

These steps occur **after constructor/property population**, before `@PostConstruct` in standard configurations, and before `InitializingBean.afterPropertiesSet()` / custom init. `ApplicationContextAware` does not work automatically in a plain `DefaultListableBeanFactory` without a context processor. Aware fields are not yet assigned inside the constructor; do not use callbacks to trigger bulk initialization of other beans before the context finishes refreshing. Lesson 185 is dedicated to the order of **all** Aware groups, `BeanPostProcessor` implementations, init/destroy, and a complete logging example.

## 7. Runnable Java 17 Example: Three Callbacks and Lifecycle

This is a standalone example using Java 17, Maven, and Spring Framework `6.2.12`. The program registers a single bean implementing all three Aware interfaces, then demonstrates callback ordering alongside `@PostConstruct`, `InitializingBean`, and a custom `initMethod`. No web server or Spring Boot is required.

Structure:

~~~text
spring-aware-demo/
├── pom.xml
└── src/main/java/example/AwareDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-aware-demo</artifactId>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

File `src/main/java/example/AwareDemo.java`:

~~~java
package example;

import jakarta.annotation.PostConstruct;

import org.springframework.beans.BeansException;
import org.springframework.beans.factory.BeanFactory;
import org.springframework.beans.factory.BeanFactoryAware;
import org.springframework.beans.factory.BeanNameAware;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.context.ApplicationContext;
import org.springframework.context.ApplicationContextAware;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class AwareDemo {

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(Config.class)) {
            AwareProbe probe = context.getBean(AwareProbe.class);
            System.out.println("8. Bean da san sang: " + probe.ready());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean(name = "awareProbe", initMethod = "customInit")
        public AwareProbe awareProbe() {
            return new AwareProbe();
        }
    }

    public static class AwareProbe
            implements BeanNameAware,
                       BeanFactoryAware,
                       ApplicationContextAware,
                       InitializingBean {

        private String beanName;
        private BeanFactory beanFactory;
        private ApplicationContext applicationContext;
        private boolean initialized;

        public AwareProbe() {
            System.out.println("1. Constructor");
        }

        @Override
        public void setBeanName(String beanName) {
            this.beanName = beanName;
            System.out.println("2. BeanNameAware: " + beanName);
        }

        @Override
        public void setBeanFactory(BeanFactory beanFactory)
                throws BeansException {
            this.beanFactory = beanFactory;
            System.out.println("3. BeanFactoryAware: "
                    + beanFactory.containsBean("awareProbe"));
        }

        @Override
        public void setApplicationContext(ApplicationContext applicationContext)
                throws BeansException {
            this.applicationContext = applicationContext;
            System.out.println("4. ApplicationContextAware: "
                    + (applicationContext != null));
        }

        @PostConstruct
        public void afterInjection() {
            boolean ok = "awareProbe".equals(beanName)
                    && beanFactory != null
                    && applicationContext != null;
            System.out.println("5. @PostConstruct: " + ok);
        }

        @Override
        public void afterPropertiesSet() {
            initialized = true;
            System.out.println("6. InitializingBean");
        }

        public void customInit() {
            System.out.println("7. Custom initMethod");
        }

        public boolean ready() {
            return initialized
                    && "awareProbe".equals(beanName)
                    && beanFactory.containsBean(beanName)
                    && applicationContext.containsBean(beanName);
        }
    }
}
~~~

Run from the `spring-aware-demo` directory:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.AwareDemo
~~~

Expected stdout printed by the program (excluding environment-specific Maven/SLF4J output):

~~~text
1. Constructor
2. BeanNameAware: awareProbe
3. BeanFactoryAware: true
4. ApplicationContextAware: true
5. @PostConstruct: true
6. InitializingBean
7. Custom initMethod
8. Bean da san sang: true
~~~

**Explanation:**

- The constructor creates `AwareProbe`, but the Aware fields do not yet have values.
- `setBeanName` receives the **registered name** `awareProbe`, not the class name `AwareProbe`.
- `setBeanFactory` receives the factory containing the definition. `containsBean("awareProbe")` returns true because the bean is already registered even while the bean itself is still initializing; this does not call `getBean()` and does not instantiate a new bean.
- `setApplicationContext` receives the context enclosing the bean. Checking non-null alone does not trigger lookups or extra work.
- By `@PostConstruct`, all three callbacks have already executed in this example's standard setup. The check simply confirms the fields are set.
- `afterPropertiesSet()` and `customInit()` run after the Aware callbacks. `ready()` is called in `main` after `AnnotationConfigApplicationContext(Config.class)` finishes refreshing.

Why doesn't the example call `applicationContext.getBean(...)` directly inside `setApplicationContext`? Because the callback happens mid-way through bean creation; fetching another bean at that moment can force additional dependency initialization, cause circular lookups, or make startup order unpredictable. In the example, it only stores the reference and checks simple state.

## 8. Are BeanFactory and ApplicationContext the Same Object?

Not necessarily. `ApplicationContext` typically uses or wraps an internal bean factory. In `AnnotationConfigApplicationContext`, `setBeanFactory` receives the `BeanFactory` used by the context, while `setApplicationContext` receives the context object. The two references belong to **two interfaces with distinct roles**, and you must not assume `beanFactory == applicationContext`.

~~~text
ApplicationContext
   │ exposes context-level APIs, events, messages, resources
   │
   └── owns / uses BeanFactory
          └── manages bean definitions, scopes, and lifecycle

BeanFactoryAware         → factory managing the bean
ApplicationContextAware  → context enclosing the bean
BeanNameAware            → registered name of that bean
~~~

`ApplicationContext` extends interfaces that allow bean lookup, yet that does not make it the low-level factory object by Java identity. Do not cast to an implementation class to modify bean definitions at arbitrary times.

## 9. Differences from `@Autowired`, `@Value`, and Constructor Injection

Constructor injection provides collaborators **when creating the object**; `@Autowired` and `@Value` support injecting/resolving dependencies or values at valid injection points through Spring infrastructure. Aware provides metadata/capabilities **after** the instance has been created. These serve different purposes, and a bean does not need to implement Aware just to receive a dependency from the container.

For example, a component that only needs to publish events can take `ApplicationEventPublisher` in its constructor and store it in a `final` field; it does not need the entire context. `BeanNameAware` provides the bean's own registered name, not a substitute for `@Qualifier` (which selects dependencies). For on-demand prototypes, inject `ObjectProvider<T>`; it respects the target's scope and does not create a new instance by default. If an adapter/framework bridge genuinely needs to leverage the full `BeanFactory` or context metadata, Aware can serve a specific purpose.

## 10. Lifecycle and AOP Risks

Aware callbacks are invoked while a bean is still initializing. Constructors cannot use fields set by `setBeanName`/`setApplicationContext`; inside setters, avoid bulk `getBean` calls as well, because they easily cause early initialization, circular dependencies, or expose incomplete singletons/proxies.

If a bean is wrapped with a Spring AOP proxy **after initialization**, Aware setters normally run on the target. Self-invocation such as `this.someTransactionalMethod()` from a setter/init method may bypass the AOP proxy, so do not treat callbacks as the place to execute transactional business logic. Receiving a context in a callback also does not guarantee that `ContextRefreshedEvent` has been published or that all listeners are ready.

With parent-child contexts, determine which context actually owns the bean; do not hold references in global statics. A singleton bean typically receives callbacks once upon creation, a prototype receives them each time a new target is created, and a closed context is no longer an active lookup source.

## 11. When to Use the Three Aware Interfaces?

| Actual Need | Appropriate Approach |
| --- | --- |
| Infrastructure needs bean name for logging/registry | `BeanNameAware` |
| Adapter needs dynamic factory bean lookup/metadata | `BeanFactoryAware` |
| Tooling needs context hierarchy or multiple context-level services | `ApplicationContextAware` |
| Service only needs repositories/gateways/mappers | Direct constructor injection |
| Singleton needs a prototype per job | Inject `ObjectProvider<T>` or an application factory |
| Only needs events, resources, or i18n | Inject `ApplicationEventPublisher`, `ResourceLoader`/`Resource`, `MessageSource` |
| Needs to run logic after startup | Lifecycle/event hook, not inside an Aware setter |

The choice should be based on **the smallest API expressing the real dependency**. `BeanNameAware` provides bean metadata, whereas `BeanFactory`/`ApplicationContext` grant container access; only use them when working with Spring infrastructure is the class's actual responsibility. Lesson 186 analyzes these trade-offs, separating adapters, and testing in detail.

## 12. Common Mistakes

### Mistake 1 — Instantiating the Object Yourself with `new`

~~~java
AwareProbe probe = new AwareProbe();
probe.ready(); // Aware fields have not been populated by the container.
~~~

Spring does not manage an object just created with `new`. To receive Aware callbacks, register the bean and let the container create/initialize the instance, or invoke lifecycle manually via specialized APIs with explicit contracts (which is uncommon in application code).

### Mistake 2 — Assuming the Bean Name Is Always the Simple Class Name

Class `AuditSink` might be registered via `@Bean("logSink")` or an alias. `setBeanName` receives the actual bean name, with no guarantee it equals `"auditSink"`. If a name has a business role, model that business data as an explicit dependency.

### Mistake 3 — Calling `getBean()` to "Self-Inject" Every Dependency

Using `BeanFactoryAware` and calling `factory.getBean(Repository.class)` everywhere hides dependencies. Prefer constructor DI and use dynamic lookup only when there is a clear need. If multiple candidates of the same type exist, lookup can also throw `NoUniqueBeanDefinitionException`; if missing, it can throw `NoSuchBeanDefinitionException`.

### Mistake 4 — Assuming `ApplicationContextAware` Always Works on a Plain BeanFactory

`DefaultListableBeanFactory` does not create an `ApplicationContext` by itself and does not invoke this callback as an `ApplicationContext` would. With `AnnotationConfigApplicationContext`, infrastructure processors are configured properly so the callback runs.

### Mistake 5 — Accessing Other Beans Too Early

Calling `getBean()` to trigger a transaction, consumer, or long-running job inside `setApplicationContext` can force other beans to instantiate at an unintended point. Aware callbacks should store needed infrastructure and return quickly.

### Mistake 6 — Confusing the BeanFactory Reference with the ApplicationContext Itself

The `BeanFactory` and `ApplicationContext` parameters have different roles and may be two distinct Java objects. Use the appropriate API instead of making unwarranted casts.

### Mistake 7 — Treating Aware Interfaces as Better Business DI Than Constructor Injection

Most application services only need business collaborators, so constructor injection is easier to read and test. Aware interfaces fit best for **infrastructure** beans that need to know about the Spring environment.

### Mistake 8 — Assuming Callbacks Fire Repeatedly on Every `getBean` Call

For a singleton, Aware callbacks normally run **once when the bean instance is created**, not on every singleton lookup. For a prototype, each newly created instance goes through wiring/lifecycle so callbacks may run multiple times. With AOP/scoped proxies, be careful to distinguish the target instance from the proxy bean.

## 13. Testing Aware Behavior Meaningfully

### 13.1. Plain Java Unit Tests

If business logic does not need the bean name or context, separate the business service so its constructor accepts normal collaborators. Test without Spring. For an infrastructure bean using Aware, unit tests can invoke setter callbacks manually with stubs or mocked `BeanFactory`/`ApplicationContext`, though such tests only validate your code and **do not prove Spring actually invokes the callbacks at the right lifecycle point**.

### 13.2. Integration Tests with a Real Context

Use an `AnnotationConfigApplicationContext` containing the bean like the example in Section 7, and verify:

- `beanName` in the callback matches the declared bean name, independent of lookup aliases.
- The factory provided to the callback contains the bean's own definition.
- The context provided to the callback matches the context that initialized the bean.
- All three callbacks ran before `@PostConstruct` and `afterPropertiesSet`.
- Calling `getBean()` multiple times on a singleton does not re-run the callbacks.
- Creating a prototype multiple times delivers separate callbacks to each target instance.

Do not assert `assertSame(context, beanFactory)`: there is no guarantee they are the same object.

### 13.3. Testing Startup Boundaries

Do not spawn a task that calls `ApplicationContext.getBean` and block waiting for it inside an Aware setter. Use integration tests with dedicated lifecycle hooks if you need to verify that the application can start/stop workers. With parent-child contexts, verify that the bean receives the context that owns it.

## 14. Self-Check Questions

**Question 1.** A class implements `BeanNameAware` and is registered via `@Bean("billingEngine")`. What does the callback receive?

**Answer:** `"billingEngine"` is the actual bean name in this case; it is not necessarily the Java class name or method name.

**Question 2.** A bean implements `BeanFactoryAware`. Is `setBeanFactory` only called after `@PostConstruct`?

**Answer:** No. This callback belongs to the pre-initialization phase; in a typical flow, it runs after property population and before `@PostConstruct`, `afterPropertiesSet`, and custom init.

**Question 3.** A bean implements `ApplicationContextAware` but only a standalone `DefaultListableBeanFactory` is used. Is it guaranteed to receive `ApplicationContext`?

**Answer:** No. A plain `BeanFactory` has no `ApplicationContext` to supply unless corresponding infrastructure is added.

**Question 4.** A constructor wants to use the `beanName` injected by `BeanNameAware`. Is that the right order?

**Answer:** No. The constructor creates the instance before any callback runs. Pass mandatory data through the constructor or wait until Aware callbacks finish before using the value.

**Question 5.** A business service only needs `CurrencyConverter`. Should it inject `ApplicationContext` and call `getBean(CurrencyConverter.class)`?

**Answer:** Usually no. Constructor injection of `CurrencyConverter` expresses the dependency directly and makes unit testing easy.

**Question 6.** Does a `ApplicationContextAware` singleton receive the context again every time someone calls `getBean()`?

**Answer:** No. Callbacks are tied to **instance** creation/initialization, whereas subsequent singleton lookups normally return the existing bean.

**Question 7.** Can `ApplicationContextAware` replace `ApplicationEventPublisherAware`?

**Answer:** `ApplicationContext` includes the event publishing API so technically yes, but if you **only need an event publisher**, injecting `ApplicationEventPublisher` or implementing `ApplicationEventPublisherAware` creates a narrower, clearer dependency.

## 15. Application Checklist

- Is the bean genuinely created and managed by Spring?
- Do you need the **bean name**, **`BeanFactory`**, **`ApplicationContext`**, or simply a business dependency?
- If needing the bean name, are you relying on aliases, generated names, or class-name assumptions?
- If needing `BeanFactory`, are you avoiding dynamic bean calls and circular dependencies inside callbacks?
- If needing `ApplicationContext`, do you actually need broad context capabilities or is there a smaller interface?
- Does the code wait for Aware callbacks instead of accessing fields inside the constructor?
- If AOP is involved, does the code avoid self-invocation and exposing the raw target too early?
- Do you distinguish one singleton bean from multiple prototype instances and multiple application contexts?
- Have you tested the real lifecycle at least once to verify callback ordering?
- Have startup jobs and resource ownership been moved to proper lifecycle hooks instead of Aware callbacks?

## 16. Official Documentation

- [Spring Framework Reference — Customizing the Nature of a Bean (ApplicationContextAware and BeanNameAware)](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Framework Reference — The BeanFactory API](https://docs.spring.io/spring-framework/reference/core/beans/beanfactory.html)
- [Spring Framework Reference — Container Extension Points](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html)
- [Spring Javadoc — BeanNameAware](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/BeanNameAware.html)
- [Spring Javadoc — BeanFactoryAware](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/BeanFactoryAware.html)
- [Spring Javadoc — ApplicationContextAware](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationContextAware.html)
