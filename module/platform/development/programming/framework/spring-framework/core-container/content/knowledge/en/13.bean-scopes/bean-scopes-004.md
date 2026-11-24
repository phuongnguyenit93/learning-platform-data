# Prototype Scope in Spring: A New Instance Each Time the Container Fulfills a Bean Request

## 1. What is Prototype?

In the Spring Framework Core Container, each **bean definition** is a recipe for the container to create an object, configure dependencies, and run initialization steps. `scope` determines whether the container reuses an existing object or creates a new one when a bean is requested.

With `prototype`, **each time the Spring IoC container actually resolves a request for a bean of that scope, the container creates and supplies a new instance**. Typical requests include:

- Calling `applicationContext.getBean(TaskState.class)` or `beanFactory.getBean("taskState")`.
- The container needing a prototype dependency to construct another bean.
- Calling `ObjectProvider<TaskState>.getObject()` to request the bean at the exact moment it is needed.
- Calling a `@Lookup` method implemented by the container to look up the bean.

Common definition:

~~~java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
TaskState taskState() {
    return new TaskState();
}
~~~

In a context where this bean is registered, two independent calls to `getBean(TaskState.class)` normally return two distinct objects. Mutable data inside the first object does not automatically appear in the second object. This is a **rule per bean lookup/resolution**, not one object per thread, per HTTP request, per transaction, or per arbitrary method call.

Compared with `singleton` (the default), prototype has key differences:

| Criterion | `singleton` | `prototype` |
| --- | --- | --- |
| Each time the container fetches the same bean definition | Returns the same instance within the context | Creates a new instance for that lookup |
| Typical initialization | At context startup if non-lazy, or when requested | When the bean is actually requested, including when needed for dependency injection |
| Mutable state | Can be shared across callers; must handle concurrency safely | Isolated across instances **unless the caller shares them** |
| Cleanup on context close | Spring invokes destroy callbacks per lifecycle rules | Spring **does not automatically invoke destroy callbacks** for prototypes handed to callers |

Two important rules: **scope is tied to the bean definition** (it does not automatically turn every `new TaskState()` into a Spring bean) and **a new instance is only created when a new bean lookup occurs**.

## 2. How does a container resolution proceed?

Consider a bean `taskState` declared as prototype. A typical request sequence:

~~~text
ApplicationContext
  ├── getBean("taskState") call 1
  │     └── create TaskState A → inject dependencies → init → return A
  ├── getBean("taskState") call 2
  │     └── create TaskState B → inject dependencies → init → return B
  └── getBean("taskState") call 3
        └── create TaskState C → inject dependencies → init → return C

A, B, C are three distinct instances.
~~~

Each time it creates an instance, Spring uses the bean definition's configuration: selecting the constructor/factory method, resolving dependencies, applying `BeanPostProcessor`s, and invoking the appropriate initialization callbacks before returning the bean. Thus `prototype` **does not mean bypassing Spring's dependency injection or initialization**.

A prototype is typically created when needed, yet concluding "if `getBean` hasn't been called, it is never created" is wrong: an eagerly initialized singleton with a prototype constructor parameter can cause the prototype to be created **as soon as the singleton is constructed**. Conversely, a prototype bean that nobody requests will not be bulk-created merely because the context ran `refresh`.

The name "prototype" is easily confused with the Prototype design pattern (cloning a template object). Spring's prototype scope **does not guarantee using `clone()`**: normally the container re-runs bean creation from the bean definition or factory method.

## 3. Runnable Java 17 Example: `getBean`, isolated state, and singletons

This example uses Spring Framework `6.2.0`, Java 17+, and Maven. Structure:

~~~text
prototype-demo/
├── pom.xml
└── src/main/java/example/PrototypeDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>prototype-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
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

File `src/main/java/example/PrototypeDemo.java`:

~~~java
package example;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;

public final class PrototypeDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            TaskState first = context.getBean(TaskState.class);
            TaskState second = context.getBean(TaskState.class);
            first.mark();

            System.out.println("Two getBean calls create two objects: " + (first != second));
            System.out.println("Independent state: "
                    + (first.value() == 1 && second.value() == 0));

            JobRunner runner = context.getBean(JobRunner.class);
            System.out.println("Runner is singleton: "
                    + (runner == context.getBean(JobRunner.class)));
            System.out.println("Directly injected dependency is retained: "
                    + (runner.injected() == runner.injected()));
            System.out.println("Provider supplies new instance each time: "
                    + (runner.fresh() != runner.fresh()));
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        public TaskState taskState() {
            return new TaskState();
        }

        @Bean
        public JobRunner jobRunner(TaskState injected,
                                   ObjectProvider<TaskState> provider) {
            return new JobRunner(injected, provider);
        }
    }

    public static final class TaskState {
        private int value;

        public void mark() {
            value++;
        }

        public int value() {
            return value;
        }
    }

    public static final class JobRunner {
        private final TaskState injected;
        private final ObjectProvider<TaskState> provider;

        public JobRunner(TaskState injected, ObjectProvider<TaskState> provider) {
            this.injected = injected;
            this.provider = provider;
        }

        public TaskState injected() {
            return injected;
        }

        public TaskState fresh() {
            return provider.getObject();
        }
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.PrototypeDemo
~~~

Expected stdout (excluding Maven environment-specific messages):

~~~text
Two getBean calls create two objects: true
Independent state: true
Runner is singleton: true
Directly injected dependency is retained: true
Provider supplies new instance each time: true
~~~

Explanation in order: the two `getBean` calls create two `TaskState` instances; incrementing the counter on the first instance does not alter the second instance. `JobRunner` is singleton by default, so fetching the runner twice gives the same reference. When building the runner, Spring created **one** `TaskState` to inject into the `injected` parameter; that field keeps the same reference across multiple `runner.injected()` calls. By contrast, each `runner.fresh()` invokes `provider.getObject()`, triggering a new prototype bean lookup.

The example uses `@Configuration(proxyBeanMethods = false)` because `@Bean` methods are resolved via the container. Do not use direct calls like `new Config().taskState()` or `config.taskState()` to test Spring bean lifecycle: a plain Java call is not equivalent to retrieving a bean through the container.

## 4. The most important case: a prototype injected into a singleton

Suppose `OrderService` is a singleton and `OrderDraft` is a prototype:

~~~java
@Component
class OrderService {
    private final OrderDraft draft;

    OrderService(OrderDraft draft) {
        this.draft = draft;
    }

    OrderDraft currentDraft() {
        return draft;
    }
}

@Component
@Scope("prototype")
class OrderDraft {
    // Draft state of an order being composed
}
~~~

This is an **illustrative snippet** assuming corresponding Spring imports, not a standalone runnable program. When Spring constructs `OrderService`, it creates one `OrderDraft` and injects that reference into the constructor. Every call to `currentDraft()` on **the same `OrderService`** returns that injected instance. Putting prototype scope on `OrderDraft` does not make the `draft` field automatically change on every method call.

If you want **a fresh draft per operation**, obtain the bean when the operation runs:

~~~java
@Component
class OrderService {
    private final ObjectProvider<OrderDraft> drafts;

    OrderService(ObjectProvider<OrderDraft> drafts) {
        this.drafts = drafts;
    }

    void placeOrder() {
        OrderDraft draft = drafts.getObject(); // Each call is a new lookup
        // Use this draft throughout one operation, then proactively release if needed.
    }
}
~~~

`ObjectProvider<T>` is supplied by Spring at the injection point; `getObject()` is when `T` is requested from the container. If `T` has prototype scope, each call provides a new bean. The provider offers additional APIs such as `getIfAvailable()` and `getIfUnique()`, yet the "new each time" behavior only holds when the bean **resolved by the provider is a prototype**, not a singleton. If you need one object used consistently throughout an operation, **call the provider once and keep a local variable**; avoid calling it again on every line that works on the same draft.

Ways to obtain a prototype inside a singleton:

| Access Pattern | When Resolved? | Result with Prototype |
| --- | --- | --- |
| Constructor/field/setter inject `T` | When the receiving bean is initialized | One instance retained via the injected reference |
| `ObjectProvider<T>.getObject()` | Each time `getObject()` is called | A new instance on each call |
| `ObjectFactory<T>.getObject()` | Each time `getObject()` is called | A new instance on each call |
| `jakarta.inject.Provider<T>.get()` | Each time `get()` is called | A new instance; requires the matching Jakarta Inject dependency |
| `ApplicationContext.getBean(T.class)` | Each time `getBean` is called | A new instance; business code depends directly on the container |
| `@Lookup` method | Each time the Spring-overridden method is called | A new instance if the looked-up bean is a prototype |

Prefer `ObjectProvider` when a singleton needs to fetch prototypes repeatedly, as it clearly expresses the intent to "fetch fresh on demand" and is easy to substitute in tests. Direct constructor injection is appropriate when only a single dependency instance is needed at the receiving bean's creation time.

## 5. Ways to configure prototype scope

**Via `@Bean` in Java configuration** (as in the runnable example above):

~~~java
@Bean
@Scope("prototype")
public TaskState taskState() {
    return new TaskState();
}
~~~

**Via component scanning**:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class WorkerTask {
    // ...
}
~~~

For the component-scanning example to take effect, the application must scan the package containing `WorkerTask` (such as via `@ComponentScan`), and the class must be registered as a Spring bean. If multiple beans of the same type are also declared, lookup by type may require `@Qualifier` or an explicit bean name.

**Via XML bean definition** in an XML-configured application:

~~~xml
<bean id="workerTask" class="example.WorkerTask" scope="prototype"/>
~~~

Note: the approaches above illustrate three different bean registration mechanisms; do not accidentally declare duplicate bean names.

## 6. Lifecycle: the container initializes prototypes but does not destroy them automatically

Each prototype creation goes through Spring's standard bean steps: constructing the instance, resolving/injecting dependencies, applying bean post-processors, invoking matching initialization callbacks (e.g., `@PostConstruct` or `InitializingBean.afterPropertiesSet()`), and then handing the object to the caller.

**Special limitation:** once Spring hands a prototype to the caller, it normally does not keep a record of that instance to invoke destruction callbacks later. When `ApplicationContext.close()` runs, Spring **does not automatically invoke** `@PreDestroy`, `DisposableBean.destroy()`, or a custom destroy method on every prototype ever created. `@PreDestroy` can be validly declared yet still not invoked automatically for prototypes as it is for singletons.

Therefore:

- If a bean holds file handles, sockets, connections, or resources that must be closed, the receiver must establish ownership conventions and close them explicitly.
- An object implementing `AutoCloseable` can be used with `try-with-resources` where the bean is fetched: `try (WorkUnit unit = context.getBean(WorkUnit.class)) { unit.execute(); }`. This is an illustrative example assuming `WorkUnit` implements `AutoCloseable`.
- A dedicated tracking and cleanup mechanism (such as a custom `BeanPostProcessor`) can be built when business requirements truly demand it; merely placing `@PreDestroy` on a prototype is not enough.
- Prototypes do not expire automatically over time. If a singleton stores prototype references in a field or long-lived collection, those instances remain alive as long as they are referenced; this can increase memory usage and hold onto resources.

Distinguish **Spring finishing bean creation** from **the application finishing bean usage**. For prototypes, the second part is the responsibility of calling code or an application-designed management mechanism.

## 7. `@Lookup` and scoped proxies: understanding "each time" precisely

### Lookup method injection

`@Lookup` lets Spring dynamically subclass a bean to override a bean-retrieval method (typically for prototypes), so the service avoids calling the container directly. Illustrative example:

~~~java
@Component
public abstract class JobService {
    public void handle() {
        WorkerTask task = newTask();
        // Use task for this processing run
    }

    @Lookup
    protected abstract WorkerTask newTask();
}
~~~

In this configuration, if `WorkerTask` is a prototype, each call to `newTask()` on the Spring-created instance fetches a new bean. Because subclassing is required, the class and overridden method cannot be `final`. Lookup method injection does not work on objects constructed and returned by a `@Bean` factory method because the container does not subclass those objects this way. The usage above is an independent illustration separate from the Maven example.

### Scoped proxy for prototypes

Configuring `@Scope(value = "prototype", proxyMode = ScopedProxyMode.TARGET_CLASS)` can inject a **stable proxy** into a singleton; **each method call through the proxy** looks up a new prototype target. This easily causes misunderstandings: two consecutive method calls on "the same proxy" can execute on **two different targets**, so data modified in the first method does not necessarily remain in the second method. If an operation must call multiple methods on the same stateful object, calling `ObjectProvider.getObject()` once and keeping a local reference is usually much clearer.

Do not confuse a prototype scoped proxy with a request-scoped proxy: a request proxy normally selects the same target within one HTTP request; a prototype proxy normally creates a new target **on each invocation**.

## 8. When to use prototype and common mistakes

Prototype is appropriate when each unit of work needs **independent mutable state** and that object must be wired/configured by Spring, such as a worker carrying state for a job or a command object being populated with data. Singleton is more appropriate for shared services/stateless components, especially when they hold no per-task state.

Common mistakes and how to check:

1. **"`@Scope("prototype")` means every method call automatically creates a new bean."** False for an ordinary prototype reference. Only a new lookup (or a proxy with special behavior) triggers creating a new instance.
2. **"Injecting a prototype once into a singleton means the singleton always gets a fresh prototype."** False. Standard constructor/field injection happens when the singleton is created. You need `ObjectProvider`, `@Lookup`, or an equivalent on-demand lookup solution.
3. **"Prototype = one bean per HTTP request."** False. Two lookups in the same request create two prototypes; `request` scope is what designs one instance per request in a web-aware context.
4. **"Prototypes are thread-safe by default."** False. Each instance starts out separate, yet if a reference is shared across multiple threads, mutable state still requires synchronization or ownership boundaries. Singleton dependencies holding shared state also require concurrency review.
5. **"Closing the context closes every allocated prototype."** False. Resources must be cleaned up according to ownership; do not rely on automatic destroy callbacks.
6. **"Manually calling `new` on an object is equivalent to `getBean`."** False. `new` bypasses wiring, post-processing, AOP proxies, and many lifecycle features performed by the container.
7. **"Prototype reduces allocations."** Usually the opposite: more lookups mean more objects. For tiny data-only objects that need no Spring wiring, instantiating plain Java objects may be simpler.
8. **"Prototype prevents memory leaks."** False. If instances are retained in unbounded caches/collections or resources are left unclosed, they are still kept alive.

### Practice Checklist

- Have you declared `prototype` on the **bean definition** and properly registered the bean in the context?
- Does the consumer need **one instance at initialization**, or **a fresh instance for each processing run**?
- Does the usage site actually perform a new lookup (`getBean`/`getObject`/`@Lookup`)?
- If multiple methods work together on one job, have you kept **the same local reference** for the entire job?
- Who is responsible for closing resources, and are prototypes retained longer than necessary?
- Have you verified behavior with `a != b` across **two independent lookups**, while confirming state is not accidentally shared through another dependency?

## 9. Self-Check Questions

**Question 1.** Bean `A` is a singleton, bean `B` is a prototype. `A` receives `B` via constructor and calls `b.run()` 10 times. How many `B` instances does Spring create solely because of those 10 `run()` calls?

**Answer:** Zero extra `B` instances are created just from calling `run()`. One `B` was created when constructing `A` and is reused; other `B` instances may exist due to lookups elsewhere.

**Question 2.** Within the same HTTP request, `context.getBean(B.class)` is called three times when `B` is a prototype. Must all three results be the same object?

**Answer:** No. There are three independent prototype lookups, so normally three distinct instances are returned.

**Question 3.** `ObjectProvider<B>` is injected into a singleton, yet `B` is actually a singleton. Do two `provider.getObject()` calls create two different objects?

**Answer:** No. The provider follows the actual scope of the requested bean; for a singleton, it returns the container-managed instance.

**Question 4.** A prototype has `@PreDestroy`. When closing `AnnotationConfigApplicationContext`, is this method guaranteed to be called for every prototype ever retrieved?

**Answer:** No. The application needs a cleanup mechanism for retrieved prototypes.

## Official References

- [Spring Framework Reference — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Spring Framework Reference — Method Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-method-injection.html)
- [Spring Framework Reference — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
