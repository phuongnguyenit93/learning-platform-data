# Spring Bean Lifecycle: Instantiation, Dependency Injection, and Initialization Steps

## 1. Goals and the Big Picture

The Spring Core Container manages objects declared as **beans**: the container knows how to create them, determine which dependencies to provide, perform configuration, invoke initialization callbacks, and (for appropriate scopes) clean up at the end of their lifecycle.

We need to separate three activities that are very easily lumped together as "initialization":

1. **Instantiation — creating the object:** creating a Java instance via a constructor, a factory method, or an appropriate instantiation mechanism.
2. **Dependency injection / property population — injecting dependencies and populating properties:** attaching the beans/values that the instance needs to function, via constructor/factory method, setter, field, or property binding depending on configuration.
3. **Initialization — initializing the bean after dependencies are available:** steps Spring invokes after populating dependencies to validate configuration, prepare data structures, or execute callbacks such as `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, and a custom `initMethod`.

A bean **already created by Java via its constructor** has not necessarily **completed initialization in Spring**. A bean is usually only ready for application code to use after Spring finishes running the required instantiation, injection, callback, and bean post-processing steps.

This is the **typical** flow for a standard bean; Spring has extension points such as `FactoryBean`, `InstantiationAwareBeanPostProcessor`, proxies, and custom scopes that can alter certain specific operations. Do not treat the simplified diagram as an immutable internal checklist for every type of bean.

~~~text
Bean definition and metadata
          │
          ▼
Container determines the bean needs to be created
          │
          ▼
Resolve dependencies for constructor / factory method
          │
          ▼
Create instance (constructor / factory method)
          │
          ▼
Inject remaining dependencies (field, setter, properties...)
          │
          ▼
*Aware callbacks and pre-initialization processing
          │
          ▼
@PostConstruct
          │
          ▼
InitializingBean.afterPropertiesSet()
          │
          ▼
Custom init method (if declared)
          │
          ▼
BeanPostProcessor post-initialization (may return a proxy)
          │
          ▼
Bean is ready for the application to retrieve and use
          │
          ▼
When scope/container ends: destroy callbacks, if managed
~~~

**Subtlety:** `@PostConstruct` is processed by a Spring `BeanPostProcessor`, so it happens **during the pre-initialization post-processor phase**. Custom `postProcessBeforeInitialization()` implementations have their own ordering; you should not assume every custom "before" callback always runs before `@PostConstruct`. The diagram places `@PostConstruct` in the right relative position with respect to `afterPropertiesSet()` and the custom init method, while omitting the ordering among different post-processors.

## 2. Where Does Spring Get Information to Create Beans?

Spring does not automatically manage every object in the JVM. It only manages beans registered through a bean definition or an equivalent mechanism.

Some common ways of registering beans:

~~~java
@Component
class OrderRepository {
}

@Service
class OrderService {
    private final OrderRepository repository;

    OrderService(OrderRepository repository) {
        this.repository = repository;
    }
}
~~~

When the package is scanned and registered by `@ComponentScan`, the container has metadata to create `OrderRepository` and `OrderService`.

Java configuration approach:

~~~java
@Configuration
class ShopConfig {
    @Bean
    OrderRepository orderRepository() {
        return new OrderRepository();
    }

    @Bean
    OrderService orderService(OrderRepository repository) {
        return new OrderService(repository);
    }
}
~~~

The short configuration snippets above are **illustrative**, not a standalone Java program with full imports and `main`; complete runnable code is in Section 7.

Common bean definition sources include `@Component`/`@Service`/`@Repository`, `@Bean` methods, XML configuration, programmatic bean registration via API, or integration frameworks. Metadata can include bean name, class/factory, scope, constructor arguments, property values, lazy flag, registration conditions, init/destroy methods, and dependency relationships.

During `ApplicationContext.refresh()`, Spring processes metadata, applies `BeanFactoryPostProcessor`/**BeanDefinitionRegistryPostProcessor** instances, registers `BeanPostProcessor` instances, and then **typically pre-instantiates non-lazy singletons**. Therefore, as soon as an `AnnotationConfigApplicationContext` is created, many singletons may have already gone through their full lifecycle, even though the application has not called `getBean()` once.

Do not confuse them:

- `BeanFactoryPostProcessor` acts on **bean definitions/container configuration before most normal beans are instantiated**.
- `BeanPostProcessor` acts on **each bean instance** at the appropriate points during creation/initialization.

If a class is not registered as a Spring bean, a `new OrderService(...)` call made directly by the application creates an ordinary Java object; Spring does not automatically run dependency injection, callbacks, or proxies for that object.

## 3. The Instantiation Step

### 3.1. Choosing a constructor or factory method

Spring must first determine how to obtain the instance.

- For a component class, Spring can invoke the class's constructor after resolving the constructor arguments.
- For a `@Bean` method, Spring invokes the corresponding factory method; the instance returned by the method becomes a managed bean and continues through the wiring/lifecycle steps.
- For specialized bean definitions or `FactoryBean`, the object creation flow can differ; you should distinguish the **factory object** from the **product supplied by the factory**.
- `InstantiationAwareBeanPostProcessor` can participate before/after instance creation, and even create a replacement proxy in certain cases.

When using constructor injection:

~~~java
@Service
class InvoiceService {
    private final InvoiceRepository repository;

    InvoiceService(InvoiceRepository repository) {
        this.repository = repository;
    }
}
~~~

Spring **must find/prepare `InvoiceRepository` before invoking the `InvoiceService` constructor**, because the constructor needs that argument. For a class with only one constructor, modern Spring can automatically use that constructor without needing `@Autowired` on the constructor. If a class has multiple constructors, choosing a constructor depends on annotations and constructor resolution rules.

At the moment the constructor body begins executing, the arguments have been passed in, but **field or setter injection on that bean itself may not have occurred yet**. In particular, `@PostConstruct` has not run yet, so you must not assume the object is completely initialized.

### 3.2. Distinguishing three levels of "the object exists"

~~~text
Constructor invoked         → Java object has been created
Dependencies populated      → Object has its references/configuration
Init callbacks completed    → Bean has been initialized by Spring
Post-processing completed   → Object Spring exposes to callers may be a proxy
~~~

This is why you should not let `this` escape from a constructor to another thread, register an asynchronous callback holding an incomplete reference, or place the instance into a static registry while the container is still wiring it. Other code could use it before dependencies/callbacks complete.

### 3.3. What happens if a constructor or factory method fails?

If a constructor throws an exception or a required dependency cannot be found, Spring cannot complete the bean creation process. The application may receive a `BeanCreationException` with a deeper cause such as `UnsatisfiedDependencyException`, `NoSuchBeanDefinitionException`, or an exception thrown by business code itself. When a required eager singleton fails to be created, context refresh usually fails.

## 4. The Dependency Injection Step

The goal of DI is **supplying collaborators and configuration from the container**, instead of having each bean create or look up those dependencies itself. Spring selects dependencies by type, bean name, qualifier, primary designation, and related autowiring rules.

### 4.1. Constructor injection

~~~java
@Service
class PaymentService {
    private final PaymentGateway gateway;

    PaymentService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Advantages: required dependencies are explicitly stated; fields can be declared `final`; easy to test by passing fakes/stubs directly; reduces the risk of an object existing in an under-initialized state without required dependencies. For indispensable dependencies, **constructor injection is usually the preferred choice**.

Timing: Spring must resolve dependencies **before** calling the constructor. If the dependencies are singletons, the container usually reuses existing singletons or creates them first. If a dependency is a prototype, each time a prototype bean is resolved for a request, an instance appropriate for that scope is supplied; injecting it once into a singleton still keeps that same reference, and it does not automatically change on each method call.

### 4.2. Setter injection

~~~java
@Component
class NotificationService {
    private EmailClient client;

    @Autowired
    public void setClient(EmailClient client) {
        this.client = client;
    }
}
~~~

Spring creates `NotificationService` first, and then during the property population step, the autowiring mechanism invokes the setter with the resolved `EmailClient` bean. When the setter runs, the object already exists, but **it has not yet reached the complete init phase**.

Setter injection fits certain configurable dependencies or cases where changing a dependency is needed, but you must check invariants: code using the bean before the setter runs may see an unset field. If not using constructor injection, `@PostConstruct` is the right place to verify that all required dependencies have been received.

### 4.3. Field injection

~~~java
@Component
class MailWorker {
    @Autowired
    private EmailClient emailClient;
}
~~~

Spring uses a post-processor such as `AutowiredAnnotationBeanPostProcessor` to populate the field after creating the instance. This style uses less code, but makes dependencies less explicit, makes plain unit-test construction harder, and is unsuitable for enforcing `final` dependencies via constructor. Consider constructor injection in application code.

### 4.4. Injection in `@Bean` factory methods

~~~java
@Bean
ReportService reportService(ReportRepository repository,
                            Clock clock) {
    return new ReportService(repository, clock);
}
~~~

In this snippet, `repository` and `clock` are **factory method parameters**, which Spring resolves before calling the method. They are similar to constructor injection in requiring "dependencies available before creating the instance", but the actual action is invoking a factory method to return the object.

Do not mix up the two concepts: calling `new Config().reportService(...)` yourself is plain Java code; Spring only manages a bean when the container itself participates in executing the bean definition.

### 4.5. Optional, collections, and qualifiers

If there are multiple beans implementing the same interface, autowiring by type alone can be ambiguous. Use `@Qualifier("beanName")`, `@Primary`, or parameter names (when metadata supports it) to disambiguate. A missing required bean causes an initialization error; for truly optional dependencies, you can use `Optional<T>` or `ObjectProvider<T>`. For collections of multiple beans, Spring supports injecting `List<T>`/`Map<String,T>` according to the corresponding rules.

`ObjectProvider<T>` lets you **defer resolving** a dependency until `getObject()` is called. Successfully injecting the provider does not guarantee that the target requested later by the provider exists in every scope context; for example, a request-scoped bean cannot be retrieved when there is no active HTTP request.

## 5. Callbacks Between DI and Initialization

After creating the bean and completing property population, Spring sends the bean through lifecycle extension points. Three groups should be distinguished:

| Extension point | Role and limitations |
| --- | --- |
| `BeanNameAware`, `BeanFactoryAware`, `ApplicationContextAware` | Lets the bean receive container information when needed; some callbacks are handled via infrastructure processors |
| `BeanPostProcessor.postProcessBeforeInitialization` | Observes/modifies the bean before standard init callbacks; `@PostConstruct` is also managed by a processor |
| `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, custom `initMethod` | Initializes the state of **the bean itself**, in this order if the three callbacks are three separate methods |
| `BeanPostProcessor.postProcessAfterInitialization` | May return the original bean or a wrapper/proxy |

For example, a bean that wants to know its bean name can implement `BeanNameAware.setBeanName(String)`. In Spring 6+, `@PostConstruct` uses `jakarta.annotation.PostConstruct` and requires annotation-processing infrastructure. It runs during the before-initialization phase, so you cannot assume **every custom** `postProcessBeforeInitialization` runs before `@PostConstruct`; the ordering of specific processors can differ.

`@Primary`, qualifiers, scope, and bean name do not themselves determine the order of init methods within **a single bean**. Callbacks should validate configuration or build lightweight state; avoid turning them into places that arbitrarily call `getBean()` or perform long business tasks. After the after-initialization step, the reference Spring returns may be a proxy distinct from the raw target. The `BeanPostProcessor` lesson covers processor ordering and proxies in depth; the lesson on combining callbacks has a dedicated trace demo.

## 6. When Is a Bean Considered Ready?

For a standard bean, after the container finishes initialization and post-processing, the instance is returned to the requester and/or cached according to the appropriate scope. Non-lazy singletons are usually already ready by the time `ApplicationContext.refresh()` completes.

Example timeline:

~~~text
T0: load bean definitions
T1: register BeanPostProcessors
T2: create singleton dependency D
T3: create singleton service S, resolve/inject D
T4: run init callbacks of S
T5: finish post-processing, possibly creating a proxy of S
T6: ApplicationContext.refresh() completes
T7: application code calls getBean(S.class), receiving the existing bean/proxy
~~~

For a `@Lazy` singleton, creation can be deferred until the bean is first actually needed (though it may still be created early if another eager singleton depends on it without a lazy proxy). For `prototype`, creation/DI/initialization happens **each time the container must create a new prototype target**. To obtain a fresh prototype per operation inside a singleton, use `ObjectProvider` or an equivalent lookup mechanism.

**Each bean being ready does not mean the whole application is ready to serve traffic.** Work that must wait until **all singletons** have been created can be placed in `SmartInitializingSingleton.afterSingletonsInstantiated()`. Work that requires the entire context to finish refreshing can react to `ContextRefreshedEvent`; tasks with their own startup/shutdown lifecycle can use `SmartLifecycle`.

In particular, do not use `@PostConstruct` to start long blocking work or complex operations accessing other beans that risk deadlock while the container holds the singleton creation lock. This hook should be short and deterministic, mainly checking state or preparing local data.

## 7. Runnable Java 17 Example: Constructor → Setter DI → Init Callbacks

The example uses **Java 17**, **Maven**, and **Spring Framework 6.2.19**. It creates beans via Java configuration, injects dependencies via constructor/factory method and setter, and then runs the callbacks in order. A destruction section is included so you can see the lifecycle boundary when closing the context.

File structure:

~~~text
spring-bean-lifecycle/
├── pom.xml
└── src/main/java/example/BeanLifecycleDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-bean-lifecycle</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
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

File `src/main/java/example/BeanLifecycleDemo.java`:

~~~java
package example;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;

import org.springframework.beans.factory.BeanNameAware;
import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class BeanLifecycleDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            ManagedJob job = context.getBean(ManagedJob.class);
            job.execute();
        } // context.close(): Spring destroys eligible singletons.
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public Repository repository() {
            return new Repository("orders");
        }

        @Bean
        public Validator validator() {
            return new Validator();
        }

        @Bean(initMethod = "customInit",
              destroyMethod = "customDestroy")
        public ManagedJob managedJob(Repository repository) {
            return new ManagedJob(repository);
        }
    }

    public static final class Repository {
        private final String name;

        public Repository(String name) {
            this.name = name;
        }

        public String name() {
            return name;
        }
    }

    public static final class Validator {
        public boolean accept(Repository repository) {
            return repository != null && !repository.name().isBlank();
        }
    }

    public static class ManagedJob
            implements BeanNameAware, InitializingBean, DisposableBean {

        private final Repository repository;
        private Validator validator;
        private String beanName;

        public ManagedJob(Repository repository) {
            this.repository = repository;
            System.out.println("1. Constructor: repository = " + repository.name());
        }

        @Autowired
        public void setValidator(Validator validator) {
            this.validator = validator;
            System.out.println("2. Setter injection: validator is set");
        }

        @Override
        public void setBeanName(String name) {
            this.beanName = name;
            System.out.println("3. BeanNameAware: " + name);
        }

        @PostConstruct
        public void postConstruct() {
            if (!validator.accept(repository)) {
                throw new IllegalStateException("Invalid dependencies");
            }
            System.out.println("4. @PostConstruct: dependencies are valid");
        }

        @Override
        public void afterPropertiesSet() {
            System.out.println("5. InitializingBean.afterPropertiesSet");
        }

        public void customInit() {
            System.out.println("6. @Bean initMethod");
        }

        public void execute() {
            if (!"managedJob".equals(beanName)) {
                throw new IllegalStateException("Wrong bean name");
            }
            System.out.println("7. Business method");
        }

        @PreDestroy
        public void preDestroy() {
            System.out.println("8. @PreDestroy");
        }

        @Override
        public void destroy() {
            System.out.println("9. DisposableBean.destroy");
        }

        public void customDestroy() {
            System.out.println("10. @Bean destroyMethod");
        }
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.BeanLifecycleDemo
~~~

Stdout printed by the program (excluding separate logs produced by the Maven environment):

~~~text
1. Constructor: repository = orders
2. Setter injection: validator is set
3. BeanNameAware: managedJob
4. @PostConstruct: dependencies are valid
5. InitializingBean.afterPropertiesSet
6. @Bean initMethod
7. Business method
8. @PreDestroy
9. DisposableBean.destroy
10. @Bean destroyMethod
~~~

**Exact explanation according to the code:**

- The `repository` bean is resolved to serve as the **factory method argument** of `managedJob(Repository repository)`; inside the factory method, the code invokes the constructor `new ManagedJob(repository)`, so line 1 appears.
- Spring creates the object first and then processes the `@Autowired` setter `setValidator`, so line 2 occurs **before** the init callbacks.
- After property population, `BeanNameAware.setBeanName` is called, producing line 3.
- The init callbacks for the same bean run in the order `@PostConstruct` → `afterPropertiesSet` → custom `initMethod`, producing lines 4, 5, and 6.
- `context.getBean(ManagedJob.class)` in `main` retrieves the ready singleton, and then the application calls `execute()`, producing line 7.
- When exiting `try-with-resources`, the context closes and invokes `@PreDestroy` → `DisposableBean.destroy` → custom `destroyMethod`, producing lines 8, 9, and 10.

In this example there is no other bean named `managedJob` and no custom `BeanPostProcessor` altering behavior. `@Autowired` and `@PostConstruct` are processed because `AnnotationConfigApplicationContext` registers the standard annotation processors. Spring may instantiate a few other infrastructure beans first, but they do not print to stdout and thus do not change the order of the 10 lines above.

Why does `@Bean(initMethod = ...)` take effect on an object created with `new` inside a factory method? Because **Spring calls the @Bean method to obtain the object**, and then **passes that object through the lifecycle process**. Meanwhile, user code calling `new ManagedJob(...)` directly outside the container will not automatically get setter injection or callbacks from Spring.

## 8. Observing BeanPostProcessor Yourself

To clearly see **another extension point** in the lifecycle, the application can register a `BeanPostProcessor`. The snippet below is an illustrative configuration; it can be placed inside the `Config` class of the example, with the corresponding imports:

~~~java
@Bean
static BeanPostProcessor tracingProcessor() {
    return new BeanPostProcessor() {
        @Override
        public Object postProcessBeforeInitialization(
                Object bean, String beanName) {
            if ("managedJob".equals(beanName)) {
                System.out.println("BPP before init");
            }
            return bean;
        }

        @Override
        public Object postProcessAfterInitialization(
                Object bean, String beanName) {
            if ("managedJob".equals(beanName)) {
                System.out.println("BPP after init");
            }
            return bean;
        }
    };
}
~~~

Import: `org.springframework.beans.factory.config.BeanPostProcessor`. **Do not add this snippet if you are comparing against the exact 10-line stdout in Section 7**, because extra trace lines will appear. This is a separate extension to observe the lifecycle.

When declaring a post-processor via `@Bean`, you should use a **static factory method** (as shown) with minimal dependencies to avoid prematurely initializing certain beans before all post-processors are registered. A `BeanPostProcessor` is usually invoked for many different beans, so the example filters by the name `managedJob`.

The line "BPP before init" should not be hard-assumed to come *before* `@PostConstruct` without controlling the ordering between `CommonAnnotationBeanPostProcessor` and the custom processor. It is guaranteed to come before callbacks like `afterPropertiesSet` and custom init under the basic contract; "BPP after init" comes after those init callbacks. A `BeanPostProcessor` returning a different object can replace/proxy the bean that clients see; do not rely on `bean == getBean(...)` if proxies are present in the application.

## 9. Singleton, Prototype, Lazy, and Impact on Lifecycle Steps

Scope and laziness affect **when** the steps are executed, without erasing the meaning of instantiation/DI/init.

| Bean type | When is it typically created? | When do DI and init happen? | When the context closes |
| --- | --- | --- | --- |
| Default singleton | During `refresh()`, if non-lazy | Once when creating the singleton | Spring executes destroy callbacks when appropriate |
| `@Lazy` singleton | When requested for the first time, unless pulled into early creation | Once when actually created | If already created and managed, destroyed when the context closes |
| Prototype | Each time the container resolves a request to create a prototype | Every created instance goes through DI/init | Spring **does not automatically invoke** destroy callbacks for each handed-out prototype |
| Request scope | When needed in the current request | Once for the target created by the scope | Cleaned up according to request and scope lifecycle |
| Session scope | When needed in the current session | Once for the target created by the scope | Cleaned up according to session and scope lifecycle |

For example, if singleton A has a constructor taking prototype B: **B is created when the container needs to construct A**, rather than waiting until the first method call on A; subsequent calls to `A.method()` do not automatically re-initialize B. If A needs a new B for each operation, use a provider/lookup on demand or a proxy mechanism with appropriate semantics.

If a new prototype is created five times, its `@PostConstruct`/`afterPropertiesSet`/`initMethod` callbacks can also be called five corresponding times. Do not use a prototype as a resource owner expecting the container to call `@PreDestroy` for each instance on application shutdown.

## 10. Caveats When Init Methods Interact with AOP, Transactions, and Threads

**Proxies/transactions:** With standard Spring AOP proxies, init callbacks run on the target before post-processing finishes. Calling `this.transactionalMethod()` from `@PostConstruct` is self-invocation and does not go through proxy advice. If you need to run transactional logic after startup, use a collaborator injected through a proxy and an appropriate lifecycle hook.

**Threads and heavy work:** Starting a thread from a constructor or init callback can expose an incompletely initialized bean. Furthermore, an init callback during singleton creation may hold a creation lock; calling many other beans, waiting on async tasks, or performing I/O without timeouts risks circular dependencies, deadlocks, and hung startup. Reserve callbacks for validation and local data structures; for work that requires all eager singletons, consider `SmartInitializingSingleton`, refresh events, or `SmartLifecycle` depending on the goal.

**Dependency cycles:** `A(B)` and `B(A)` via constructors have no valid construction order. Blindly switching to field/setter injection may merely mask a coupled design, and settings that allow circular references vary by environment. Clarify dependency contracts, split responsibilities, or use intentional lazy lookup. A dedicated section on pitfalls in init callbacks will illustrate locks, timeouts, and safe ways to start background tasks.

## 11. Common Errors and How to Diagnose Them

| Symptom | Possible cause | How to check/fix |
| --- | --- | --- |
| `@PostConstruct` does not run | Class created with `new` outside Spring; wrong annotation package; processor not registered | Ensure the object is a Spring bean; use `jakarta.annotation.PostConstruct` with Spring 6; check context configuration |
| `@Autowired` setter is not called | Bean does not go through autowiring processor or is not managed by the right context | Check bean registration and annotation processors |
| `NullPointerException` in constructor when accessing `@Autowired` field | Field injection has not happened yet | Move required dependencies to the constructor |
| Bean appears to run init twice | Two instances/contexts exist, different proxy/lifecycle, or code calls callback manually | Log bean name, context identity, and instantiation site; do not call init methods manually |
| Cannot resolve dependency | No bean, multiple candidates, wrong qualifier/generic | Read the cause of `UnsatisfiedDependencyException`/`NoUniqueBeanDefinitionException`; add bean or qualifier |
| Bean does not initialize at app start | `@Lazy`/prototype or condition did not register it | Check scope, lazy flag, and whether anything has requested the bean |
| Bean is initialized "too early" | Eager singleton or another bean's dependency pulled it into creation | Inspect the dependency graph and `@Lazy` scope |
| `@Transactional` does not work inside `@PostConstruct` | Init runs on the target before entering through the AOP entry point | Move logic to after the proxy is ready, calling through another bean/proxy |
| Context startup fails during init | Callback throws an exception, invalid I/O/validation | Inspect the root exception in `BeanCreationException`, check parameters and config |
| Prototype does not run `@PreDestroy` on context close | Spring does not manage the destroy phase of handed-out prototypes | Establish a convention where the recipient closes the resource |
| Order of independent beans differs from expectation | No arbitrary order is guaranteed among beans without dependencies | Do not rely on accidental order; declare real dependencies or use appropriate app lifecycle hooks |
| Plain `new` test differs from Spring context test | Unit test has no container wiring | Pass collaborators manually or run a Spring test context when lifecycle testing is needed |

**When debugging, place controlled logs in constructors, setters, `@PostConstruct`, init callbacks, and business methods**; distinguish when the bean is created from when requests call `getBean()`. In an AOP context, you can also print the class of the object provided by the context to recognize proxies, though you should not rely on generated proxy class names as an API contract.

## 12. Practical Checklist and Exercises

Before considering a bean properly configured, check yourself:

1. Does the bean definition come from component scanning, `@Bean`, XML, or an API registration? Is the object truly managed by the container?
2. What are the bean's scope and laziness? What triggers the first instance creation?
3. Are required dependencies available in the constructor/factory method? Which dependencies are only injected via setter/field afterward?
4. Is an injected field used in the constructor before injection takes place?
5. Does the init callback only validate/configure local state, or is it doing risky/overly heavy work?
6. If multiple callbacks coexist, is the order `@PostConstruct` → `afterPropertiesSet` → custom init understood?
7. Is the bean replaced by a proxy after init? Is AOP advice being invoked inside a constructor/init/self-invocation?
8. Have the resource owner and the destroy mechanism corresponding to the scope been identified?
9. On error, do you read the **root cause** of `BeanCreationException` to see whether the failure occurred during instantiation, DI, or initialization?

### Exercise 1 — Constructor and field injection

A component has a constructor calling `emailSender.send()`, while `emailSender` is only annotated with `@Autowired` on a field. Where can the error happen?

**Answer:** The constructor runs before field injection, so `emailSender` may still be `null`. If the dependency is required, move `EmailSender` into a constructor argument.

### Exercise 2 — Order of init callbacks

A bean has three separate methods using `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, and `@Bean(initMethod="prepare")`. What is the invocation order?

**Answer:** `@PostConstruct` → `afterPropertiesSet()` → `prepare()`, assuming the bean is created and populated with dependencies successfully.

### Exercise 3 — Singleton and the second `getBean()` call

A non-lazy singleton was already created by Spring during context refresh. Later, `getBean(MyService.class)` is called twice. Do constructor, DI, and init run two more times?

**Answer:** No. Both lookups normally return the same already-initialized singleton; the bean is not created or initialized again.

### Exercise 4 — Prototype received by a singleton

`SingletonWorker` receives a `PrototypeTask` via its constructor. Does each call to `worker.perform()` automatically inject a new `PrototypeTask`?

**Answer:** No. The dependency is resolved once when constructing `SingletonWorker`. To create a new prototype per operation, retrieve it on demand with `ObjectProvider<PrototypeTask>` or an appropriate factory.

### Exercise 5 — Post-processor and @PostConstruct

Can you be certain that every custom `BeanPostProcessor.postProcessBeforeInitialization` runs before `@PostConstruct`?

**Answer:** No. `@PostConstruct` is processed via a Spring BeanPostProcessor; the ordering of post-processors affects their relative positions. Only rely on guaranteed contracts/ordering.

## 13. Official References

- [Spring Framework — Customizing the Nature of a Bean (Lifecycle Callbacks)](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Framework — Container Extension Points: BeanFactoryPostProcessor and BeanPostProcessor](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html)
- [Spring Framework — Using @PostConstruct and @PreDestroy](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/postconstruct-and-predestroy-annotations.html)
- [Spring Framework — Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
