# How Scope Determines the Relationship Between Definition and Instance in the Spring Core Container

## 1. Why doesn't a bean definition tell you how many objects exist?

In the Spring Framework, a **bean definition** is the recipe that tells the container **how to create, configure, and manage a bean**. From the same bean definition, the container can return **a single shared object** or **multiple distinct objects** depending on the **scope**. Therefore, two questions must be kept separate:

1. **Definition:** Which bean metadata has Spring registered, how is it created, and what are its dependencies?
2. **Instance:** When the application requests the bean, which object does Spring return, is it newly created or reused, and within what boundary does that object exist?

Example:

```java
@Configuration(proxyBeanMethods = false)
class AppConfig {
    @Bean
    CatalogService catalogService() {
        return new CatalogService();
    }
}
```

This is a short snippet, not a standalone runnable program. `catalogService` belongs to the **singleton scope** by default, so each `catalogService` bean definition in a typical Spring IoC container is associated with only **one managed singleton object**.

However, if you change it to:

```java
@Bean
@Scope("prototype")
CatalogService catalogService() {
    return new CatalogService();
}
```

the same factory method declaration can create **multiple `CatalogService` objects**, each time the container receives a request for the prototype bean.

**The core point of this topic:** Scope is not the name of a Java class type; it is the **mapping policy between a bean definition and its instances**, along with the object's usage boundary and lifecycle.

### Learning Objectives

After this lesson, you will:

- Understand that `BeanDefinition` is metadata/a factory recipe, not identical to an object.
- Know the standard scopes: `singleton`, `prototype`, `request`, `session`, `application`, `websocket`.
- Distinguish Spring's singleton **per bean, per container** from the GoF Singleton using a static global instance.
- Understand that bean creation timing, eager/lazy behavior, and scope are **orthogonal dimensions**.
- Know why a singleton injecting a prototype via constructor still retains **the exact single prototype instance it received**.
- Use `ObjectProvider<T>`/`ObjectFactory<T>` or a scoped proxy for short-lived dependencies.
- Recognize that request/session scopes require a **web-aware `ApplicationContext`** and do not work automatically in a plain context.
- Understand that prototype destruction callbacks **are not automatically invoked by Spring when the context closes**.
- Write `@Scope`, `@RequestScope`, `@SessionScope`, XML scopes, and configure custom scopes.
- Experiment with Java 17/Spring Framework 6.2 with exact output, demonstrating singleton identity and prototype multiplicity.
- Avoid scope mismatch bugs, stale request state, memory leaks, and improper lifecycle dependencies.

## 2. The Model from Definition to Instance

A bean definition includes attributes such as:

- Bean name/aliases.
- Java class, constructor, or factory method.
- Constructor/property dependencies.
- Scope.
- Lazy initialization.
- Initialization/destruction callbacks.
- Qualifiers, primary, role, and other metadata.

The `BeanFactory` reads/encounters the definition and acts according to its scope:

```text
                         BeanDefinition
            name = "jobUnit", class = JobUnit
            scope = singleton or prototype
                              |
              +---------------+----------------+
              |                                |
              v                                v
         singleton scope                 prototype scope
        +----------------+               +----------------+
request #1 ---> object A                 request #1 ---> object A
request #2 ---> object A                 request #2 ---> object B
request #3 ---> object A                 request #3 ---> object C
        +----------------+               +----------------+
              |                                |
              v                                v
       One shared object                Multiple objects created from
       per bean/container               the same recipe
```

The phrase "request #1/#2" in the diagram refers to **a `BeanFactory` lookup request for the bean**, not necessarily an HTTP request. The HTTP `request` scope will be explained separately.

### 2.1. A definition can exist without an instance yet

```java
boolean registered =
        context.getBeanFactory().containsBeanDefinition("jobUnit");
boolean singletonPresent =
        context.getBeanFactory().containsSingleton("jobUnit");
```

This snippet only works when `context` is an appropriate `ConfigurableApplicationContext` and `jobUnit` has already been declared. `containsBeanDefinition` checks the definition in the local registry; `containsSingleton` checks whether a singleton instance has been registered in the singleton registry. The two results are not always the same.

A prototype definition can exist in the registry without having a singleton instance, because **prototypes are not cached like singletons**.

### 2.2. One class can have multiple bean definitions

```java
@Bean("primaryClient")
Client clientA() {
    return new Client("primary");
}

@Bean("backupClient")
Client clientB() {
    return new Client("backup");
}
```

Both definitions return the `Client` class, yet if both are singletons, Spring still manages **two distinct singleton bean objects** — each bean name has its own definition and cache entry.

Do not interpret "singleton" as "one instance per Java class". The Spring docs refer to this characteristic as **per-container and per-bean**.

### 2.3. A Java object is not necessarily a managed bean

```java
Client manual = new Client("manual");
```

If you use `new` yourself, this object **does not automatically** receive a `BeanDefinition`, scope, injection, initialization callbacks, or Spring destruction callbacks. An object whose class matches a managed bean's class can still reside **outside the container**.

## 3. Table of Standard Scopes

Spring Framework 6.2 supports the following scopes:

| Scope | Instance Boundary | When to Apply? |
| --- | --- | --- |
| `singleton` | One managed object per bean definition per Spring IoC container | Default scope, typically for services/stateless collaborators |
| `prototype` | Each `BeanFactory` request for the bean can create a new instance | Short-lived stateful objects, each for a separate use |
| `request` | One object per HTTP request | State tied to the request being processed |
| `session` | One object per HTTP session | State tied to a user/HTTP session |
| `application` | One object per `ServletContext` | Shared state within a web application/servlet context |
| `websocket` | One object per corresponding WebSocket session | Components tied to a WebSocket/STOMP session |
| Custom scope | Determined by the `Scope` implementation | Tenant, conversation, or a custom lifecycle model |

The four web scopes **request, session, application, websocket** require a corresponding **web-aware `ApplicationContext`**. A plain `AnnotationConfigApplicationContext` in a console program does not automatically enable these scopes.

Spring also provides `SimpleThreadScope` in the library, but it is **not registered by default**. Do not treat `thread` as one of the six standard scopes automatically available in every context.

### Terminology Warning

A "request" in `request scope` is an **HTTP request**; a "request for a prototype bean" is a **`BeanFactory` resolve/`getBean` call**, not an HTTP request. One HTTP request can call `getBean` multiple times; requests for a prototype will receive multiple instances unless another mechanism holds the reference.

## 4. Singleton: one shared instance per definition/container

### 4.1. Java syntax

```java
@Configuration(proxyBeanMethods = false)
class Config {
    @Bean
    SharedCatalog sharedCatalog() {
        return new SharedCatalog();
    }
}
```

`singleton` is the default scope, so `@Scope("singleton")` is unnecessary. If you want to be explicit:

```java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_SINGLETON)
SharedCatalog sharedCatalog() {
    return new SharedCatalog();
}
```

These are two separate illustrative snippets; do not put both definitions with the same name into one real class. `ConfigurableBeanFactory` belongs to `org.springframework.beans.factory.config`.

### 4.2. XML syntax

```xml
<bean id="sharedCatalog" class="example.SharedCatalog"/>
```

is equivalent to the default scope declaration, and:

```xml
<bean id="sharedCatalog"
      class="example.SharedCatalog"
      scope="singleton"/>
```

is the explicit form. A real XML file requires a root `<beans>` element and valid namespaces/schemas.

### 4.3. Singleton identity

```java
Object first = context.getBean("sharedCatalog");
Object second = context.getBean("sharedCatalog");
boolean same = first == second;
```

For a regular singleton, `same` is `true`. Two alias names pointing to the same singleton definition can also return the exact same object. However, if retrieving a `FactoryBean` or AOP proxy, you must distinguish whether the object being retrieved is the **factory, product, or proxy** when examining identity.

### 4.4. Differences from the GoF Singleton

The GoF Singleton pattern typically places a static global holder/restricted constructor inside the Java class. A Spring singleton:

- Maps by **bean name/definition + `BeanFactory`**.
- Allows multiple singleton definitions of the same class.
- Can have a separate instance in each `ApplicationContext`.
- Does not force the Java class to use a static holder/private constructor.
- Can be wrapped in a proxy by Spring.
- Has its injection/lifecycle managed by Spring.

Saying "singleton service" in Spring generally does not mean "that Java class is allowed to be instantiated only once across the entire JVM".

### 4.5. Singleton does not mean thread-safe

Multiple requests/threads can use the same singleton bean. Scope only defines **shared object identity**; it does not automatically synchronize mutable fields:

```java
// Anti-pattern for non-thread-safe mutable state.
class UnsafeCounter {
    private int count;
    int next() {
        return ++count;
    }
}
```

If a singleton bean is called concurrently, `++count` can lose updates. Use immutable state or concurrency primitives such as `AtomicInteger` when shared mutation is genuinely needed. For request-specific data, do not store it directly in fields of a singleton service.

## 5. Prototype: one bean definition creates multiple instances

`prototype` is commonly used for stateful objects or job/request objects with clear ownership.

### 5.1. Java configuration

```java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
JobUnit jobUnit() {
    return new JobUnit();
}
```

Or:

```java
@Component
@Scope("prototype")
class JobUnit {
}
```

These two snippets are **two alternative ways of registering** the bean; do not apply both to the same class in one context unless you intentionally want two definitions.

### 5.2. XML

```xml
<bean id="jobUnit"
      class="example.JobUnit"
      scope="prototype"/>
```

### 5.3. Each lookup of a prototype can create a new object

```java
JobUnit first = context.getBean(JobUnit.class);
JobUnit second = context.getBean(JobUnit.class);

System.out.println(first == second); // false in typical cases
```

However, this is only true if `JobUnit` is registered by Spring as a prototype and there is no wrapper/provider layer changing the semantics of the object you are comparing.

### 5.4. Prototype is not "one object per HTTP request"

If a service calls `getBean(prototypeName)` three times within the same HTTP request, there are normally three prototype instances. If you need **one instance reused across lookups within the same HTTP request**, use `request` scope instead of prototype.

### 5.5. Prototypes are created on demand

`BeanFactory` typically does not create all prototype instances during `ApplicationContext.refresh()`. However, an eager singleton that requires a prototype as a constructor dependency will cause the container to create **one prototype object** as soon as the singleton is constructed. See section 7.

## 6. Bean definition, scope, and lazy/eager are three different axes

These three properties are related but not synonymous:

- **Definition:** Has the recipe/metadata been registered yet?
- **Scope:** How many instances and what is the sharing boundary?
- **Laziness:** When does the container proactively create a singleton bean?

Example:

```java
@Bean
@Lazy
SharedCatalog sharedCatalog() {
    return new SharedCatalog();
}
```

This is still **singleton scope**. `@Lazy` only allows the container to defer creation until first use, unless an eager dependency requires it earlier.

`prototype` is different: a new object typically appears on each lookup, rather than having a single singleton waiting to be created lazily.

| Definition | Scope | Lazy? | Approximate Meaning |
| --- | --- | --- | --- |
| `sharedCatalog` | singleton | false | One bean pre-instantiated in a typical `ApplicationContext` |
| `rareClient` | singleton | true | One singleton created when actually requested |
| `jobUnit` | prototype | depends on metadata | A new instance each time it is requested |
| `requestState` | request | cannot be interpreted as eager singleton | One instance per active HTTP request |
| `userPrefs` | session | depends on active session | One instance per HTTP session |

Do **not** assume that changing `@Lazy` to `@Scope("prototype")` optimizes "the same thing". One changes timing; the other changes identity/multiplicity and lifecycle.

## 7. Common Pitfall: a singleton injecting a prototype only once

Consider the configuration:

```java
@Bean
@Scope("prototype")
TaskUnit taskUnit() {
    return new TaskUnit();
}

@Bean
TaskProcessor taskProcessor(TaskUnit taskUnit) {
    return new TaskProcessor(taskUnit);
}
```

`taskProcessor` is a default singleton; Spring only invokes the `taskProcessor(TaskUnit)` factory method when creating the singleton. At that moment, `BeanFactory` supplies **one** prototype `TaskUnit`. The processor holds onto that exact reference:

```text
BeanDefinition taskUnit, scope=prototype
           |
           | one dependency request when creating taskProcessor
           v
      TaskUnit instance #1 -----------+
                                       |
                                       v
                           TaskProcessor singleton
                                       |
                  method run() call 1 / call 2 / call 3
                                       |
                                       v
                            still uses TaskUnit #1
```

Therefore, if `TaskProcessor.run()` expects a **fresh** task state object **for every execution**, directly constructor-injecting the prototype has the wrong semantics.

### 7.1. This does not turn the prototype into a singleton

The `taskUnit` bean definition **still belongs to the prototype scope**. Other `context.getBean(TaskUnit.class)` calls can create `TaskUnit` #2, #3. However, the object that the singleton processor **already holds** is not automatically replaced when running the method.

### 7.2. Fixing with ObjectProvider

```java
import org.springframework.beans.factory.ObjectProvider;

final class TaskProcessor {
    private final ObjectProvider<TaskUnit> taskUnits;

    TaskProcessor(ObjectProvider<TaskUnit> taskUnits) {
        this.taskUnits = taskUnits;
    }

    void run() {
        TaskUnit fresh = taskUnits.getObject();
        fresh.process();
    }
}
```

This illustrative snippet requires a `TaskUnit` class with a `process()` method. Now the processor holds the provider; each `getObject()` call performs **a new bean lookup**, matching prototype semantics.

### 7.3. ObjectFactory and jakarta.inject.Provider

Spring provides `ObjectFactory<T>` with `getObject()`. `ObjectProvider<T>` extends lookup capabilities with `getIfAvailable()`, `getIfUnique()`, streams, and other methods. `jakarta.inject.Provider<T>` provides `get()` if integrating with that dependency.

Choose which type to use based on actual semantics. Do not inject `ApplicationContext` into all business services just to call `getBean` by string: that is service-locator coupling and makes testing harder.

### 7.4. @Lookup method injection

Spring also supports `@Lookup` for lookup-method injection:

```java
abstract class BatchRunner {
    public void run() {
        TaskUnit fresh = newTaskUnit();
        fresh.process();
    }

    @Lookup
    protected abstract TaskUnit newTaskUnit();
}
```

This illustrative snippet requires Spring to create/enhance `BatchRunner` using the method injection mechanism. **Do not apply it arbitrarily to objects created by `@Bean` factory methods or objects instantiated with `new` outside the container**: Spring needs to control instantiation/enhancement; `final` methods/classes or other constraints can prevent injection from working. In many designs, `ObjectProvider<T>` is simpler and more transparent.

### 7.5. Prototype via scoped proxy

If Spring injects a **scoped proxy** for a prototype into a singleton, *each method invocation through the proxy* can create a new prototype target. This is different semantics from "one new prototype per business operation consisting of multiple method calls".

If an operation needs to call `prepare()` and `execute()` **on the same `TaskUnit`**, calling two independent methods through a prototype scoped proxy may act on **two different targets**. Use a provider to obtain the object once at the beginning of the operation, then invoke both methods on the same reference.

## 8. Runnable Java 17 Example: singleton, prototype, and provider

This complete example uses **Spring Framework 6.2.19**, Java 17, and Maven, requiring no Spring Boot, server, database, or network at runtime.

It demonstrates:

1. The `SharedCatalog` singleton returns the same reference.
2. An eager singleton `FixedConsumer` was injected with a prototype `TaskUnit` during context refresh.
3. Two `getBean(TaskUnit.class)` calls create new prototype instances.
4. The `DynamicConsumer` singleton holds an `ObjectProvider<TaskUnit>` to obtain a new prototype on each call.
5. `RareTool` is a lazy **singleton**: not created after refresh, created on first use, and then returns the same reference.
6. Singletons, prototypes, and providers all originate from **single bean definitions per bean name**.

### 8.1. Structure

```text
scope-recipe-demo/
├── pom.xml
└── src/main/java/demo/
    └── ScopeRecipeDemo.java
```

### 8.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>scope-recipe-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
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
```

### 8.3. Full Java source

Create `src/main/java/demo/ScopeRecipeDemo.java`:

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;
import org.springframework.context.annotation.Scope;

public class ScopeRecipeDemo {

    public static final class Sequence {
        private final AtomicInteger next = new AtomicInteger();

        public int nextId() {
            return next.incrementAndGet();
        }
    }

    public static final class SharedCatalog {
        public String name() {
            return "catalog-ready";
        }
    }

    public static final class TaskUnit {
        private final int id;

        public TaskUnit(int id) {
            this.id = id;
        }

        public int id() {
            return id;
        }
    }

    public static final class FixedConsumer {
        private final TaskUnit taskUnit;

        public FixedConsumer(TaskUnit taskUnit) {
            this.taskUnit = taskUnit;
        }

        public int assignedId() {
            return taskUnit.id();
        }

        public TaskUnit taskUnit() {
            return taskUnit;
        }
    }

    public static final class DynamicConsumer {
        private final ObjectProvider<TaskUnit> tasks;

        public DynamicConsumer(ObjectProvider<TaskUnit> tasks) {
            this.tasks = tasks;
        }

        public int newTaskId() {
            return tasks.getObject().id();
        }
    }

    public static final class LazyMarker {
        private boolean created;

        public void mark() {
            created = true;
        }

        public boolean created() {
            return created;
        }
    }

    public static final class RareTool {
        public RareTool(LazyMarker marker) {
            marker.mark();
        }

        public String label() {
            return "rare-ready";
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public Sequence sequence() {
            return new Sequence();
        }

        @Bean
        public SharedCatalog sharedCatalog() {
            return new SharedCatalog();
        }

        @Bean
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        public TaskUnit taskUnit(Sequence sequence) {
            return new TaskUnit(sequence.nextId());
        }

        @Bean
        public FixedConsumer fixedConsumer(TaskUnit taskUnit) {
            return new FixedConsumer(taskUnit);
        }

        @Bean
        public DynamicConsumer dynamicConsumer(
                ObjectProvider<TaskUnit> tasks) {
            return new DynamicConsumer(tasks);
        }

        @Bean
        public LazyMarker lazyMarker() {
            return new LazyMarker();
        }

        @Bean
        @Lazy
        public RareTool rareTool(LazyMarker marker) {
            return new RareTool(marker);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            SharedCatalog catalog1 =
                    context.getBean(SharedCatalog.class);
            SharedCatalog catalog2 =
                    context.getBean(SharedCatalog.class);
            FixedConsumer fixed =
                    context.getBean(FixedConsumer.class);
            DynamicConsumer dynamic =
                    context.getBean(DynamicConsumer.class);
            LazyMarker marker =
                    context.getBean(LazyMarker.class);

            System.out.println("catalog=" + catalog1.name());
            System.out.println("singletonSame=" + (catalog1 == catalog2));
            System.out.println("fixedTaskId=" + fixed.assignedId());

            TaskUnit task2 = context.getBean(TaskUnit.class);
            TaskUnit task3 = context.getBean(TaskUnit.class);
            System.out.println("directPrototypeIds=" +
                    task2.id() + "," + task3.id());
            System.out.println("directPrototypeDifferent=" +
                    (task2 != task3));
            System.out.println("fixedStillFirst=" +
                    (fixed.assignedId() == 1));

            System.out.println("providerPrototypeIds=" +
                    dynamic.newTaskId() + "," + dynamic.newTaskId());

            System.out.println("lazyBeforeLookup=" +
                    marker.created());
            RareTool rare1 = context.getBean(RareTool.class);
            RareTool rare2 = context.getBean(RareTool.class);
            System.out.println("rare=" + rare1.label());
            System.out.println("lazyAfterLookup=" +
                    marker.created());
            System.out.println("lazySingletonSame=" +
                    (rare1 == rare2));
        }
    }
}
```

### 8.4. Running

```bash
mvn -q clean compile exec:java -Dexec.mainClass=demo.ScopeRecipeDemo
```

The project may require Maven to download dependencies on the first run; the program does not depend on the network once the required JARs are present.

### 8.5. Expected Output

Lines **printed by the program's `System.out.println`**, excluding environment-dependent logs:

```text
catalog=catalog-ready
singletonSame=true
fixedTaskId=1
directPrototypeIds=2,3
directPrototypeDifferent=true
fixedStillFirst=true
providerPrototypeIds=4,5
lazyBeforeLookup=false
rare=rare-ready
lazyAfterLookup=true
lazySingletonSame=true
```

### 8.6. Why are the IDs exact?

`Sequence` is a singleton holding the **context's** own `AtomicInteger`. Creating the eager `FixedConsumer` bean requires the `TaskUnit` prototype, so Spring invokes the `taskUnit(sequence)` factory for the first time and assigns **id=1**.

No other eager bean needs `TaskUnit` right at startup. `DynamicConsumer` only holds an `ObjectProvider<TaskUnit>`, without fetching a prototype when the dynamic consumer's constructor/factory method runs.

After refresh, the two `context.getBean(TaskUnit.class)` calls create new instances **id=2** and **id=3**. The two `dynamic.newTaskId()` calls invoke the provider and create **id=4** and **id=5** next.

`fixed.assignedId()` remains 1 because the `FixedConsumer` singleton holds the first `TaskUnit` reference. This is the phenomenon of **a singleton lifetime outliving an injected prototype's lifetime**, not Spring accidentally turning a prototype into a singleton.

### 8.7. Why isn't RareTool created beforehand?

`RareTool` is a lazy singleton declared with `@Lazy` on `@Bean`. No eager bean in the demo requires `RareTool`. The eager `LazyMarker` may be created beforehand, but having the marker **does not** automatically trigger `RareTool`. Thus `marker.created()` is false before `getBean(RareTool.class)` and true afterward; both lookups return the same singleton.

### 8.8. Why doesn't the output depend on creation order of unrelated beans?

Sequence IDs are only assigned in the `TaskUnit` factory. Creating `FixedConsumer` requires creating one `TaskUnit`; the other `TaskUnit` instances are only requested via explicit `getBean` and `provider.getObject` calls in `main`. Other beans do not create `TaskUnit`, so there is no dependency on their creation order. There are no static global IDs or background threads.

### 8.9. Key point about @Configuration(proxyBeanMethods=false)

Factory methods receive dependencies via **parameters**, rather than directly calling another factory method. This ensures that `BeanFactory` determines bean identity/scope. If you wrote `return new FixedConsumer(taskUnit(sequence()))` in lite configuration, direct Java factory method calls could create objects outside the container, breaking the semantics the demo is teaching.

## 9. Scope and dependency injection: watch out for long/short lifetimes

A common architectural issue is a **long-lived bean** holding a reference to a **short-lived bean**:

```text
Singleton Service
      |
      | injected directly when singleton is created
      v
Prototype / Request / Session Bean
      |
      +--> Concrete object is retained across multiple calls
```

This causes two kinds of bugs:

1. **Unintended prototype reuse:** the singleton receives only one prototype object at initialization time.
2. **Invalid or stale request/session scope:** a singleton cannot directly hold a request-specific object and reuse it across all HTTP requests/users.

### 9.1. If the dependency truly has the same lifetime

Direct injection is fine. For example, a singleton service holding a singleton repository makes sense; both objects share the same container boundary.

### 9.2. If the dependency is shorter-lived than the consumer

You can:

- Use `ObjectProvider<T>` and resolve the target per operation.
- Inject a **scoped proxy** instead of the target object directly.
- Pass request-specific data as **method parameters** from the controller/use-case layer.
- Redesign the interface to separate mutable state out of the singleton service.
- Use method injection if appropriate, while noting its constraints.

### 9.3. A better approach for request-specific business data

Instead of storing `currentUserId` in a singleton service field:

```java
// Anti-pattern:
class UnsafeOrderService {
    private String currentUserId;

    public void setCurrentUserId(String userId) {
        currentUserId = userId;
    }
}
```

pass the data to the service method:

```java
class OrderService {
    public String createOrder(String userId, String sku) {
        return userId + ":" + sku;
    }
}
```

These are two separate illustrative designs. A stateless service contains no per-request mutable state, making it easier to share across threads and tests.

## 10. Request scope: one bean per HTTP request

In a web-aware `ApplicationContext` with an active HTTP request, a `request` bean has **one target per request**. Two usages of the same bean within one request receive the same target; the next request gets a new target. `@RequestScope` uses a class-based scoped proxy by default, so a singleton controller can hold the proxy and delegate to the current target when handling HTTP requests.

~~~java
@Component
@RequestScope
class RequestTrace {
    private final String traceId =
            java.util.UUID.randomUUID().toString();

    String id() {
        return traceId;
    }
}
~~~

This snippet only illustrates one bean in a Spring Servlet environment; it requires the `Component` and `RequestScope` imports and proper component scanning. The `traceId` value is initialized once per target, so calls to `id()` within the same HTTP request return the same result. The dedicated lesson on web scopes provides a complete HTTP example for verification.

## 11. Session scope: per HTTP session, not permanently per user account

`@SessionScope` binds a target to **one HTTP session**: multiple requests carrying the same session ID normally share the target, while different sessions have separate targets. One user may open multiple sessions; multiple tabs sharing the same cookie may share one session. For mutable state, you must consider concurrency across HTTP requests in the same session, memory pressure, timeouts, and serialization/persistence when required by the infrastructure.

## 12. Application scope differs from singleton scope

`@ApplicationScope` stores the target in the **`ServletContext`**; `singleton` belongs to the **bean definition/container**. One `ServletContext` can be associated with multiple Spring contexts, while different JVMs/pods do not automatically share memory. Both scopes can be accessed by multiple threads, so keep state immutable/stateless or protect mutations appropriately.

## 13. WebSocket scope

`websocket` manages targets per **WebSocket/STOMP session** in the appropriate messaging infrastructure, distinct from HTTP request/session. Each connection has its own state; multiple messages on the same connection can access the same target and still require concurrency design. Spring 6.x can declare `@Scope("websocket", proxyMode = ScopedProxyMode.TARGET_CLASS)` when a STOMP broker is configured; the `@WebSocketScope` annotation belongs to Spring 7.x.

## 14. Scoped proxy: same reference in consumer, target changes by scope

A singleton consumer has a longer lifetime than a request/session bean. A **scoped proxy** allows holding a stable proxy reference while resolving the target according to the currently active request/session on each method call. With `ScopedProxyMode.INTERFACES`, the injection point uses an interface; `TARGET_CLASS` creates a subclass proxy and is subject to `final` class/method limitations. Do not access a request target outside an active request.

~~~java
// Snippet in web-aware Spring configuration; RequestIdentityImpl implements RequestIdentity.
@Bean
@Scope(value = "request", proxyMode = ScopedProxyMode.INTERFACES)
RequestIdentity requestIdentity() {
    return new RequestIdentityImpl();
}
~~~

The proxy is injected into the singleton; across two HTTP requests, the proxy reference may be the same while the underlying target differs. Avoid caching the actual target in a singleton field.

## 15. ObjectProvider and scoped proxy: choose by semantics

- **Scoped proxy**: the consumer invokes the collaborator like a normal interface/class; the proxy selects the target at method call time, well-suited for request/session beans.
- **`ObjectProvider<T>`**: the consumer explicitly calls `getObject()` when needed, and can then hold the target in a local variable throughout a business operation.
- With a **prototype scoped proxy**, two method calls can create two different prototype targets. If `prepare()` and `commit()` must operate on the same instance, obtain the prototype **once** via a provider and call both methods on it.

## 16. Lifecycle: Spring does not destroy prototypes like singletons

Spring initializes singletons/prototypes according to the bean lifecycle, but for prototypes it **does not automatically execute destruction callbacks** when `ApplicationContext.close()` runs; the caller or a separate owner must `close()` any required resources. Singletons have their destruction managed by Spring with the context when valid callbacks exist. Request/session targets follow the lifecycle of the supported web scope—not every Spring bean disappears simply because an HTTP request ends.

Example: an `AutoCloseable` prototype obtained via a provider can use `try (var session = provider.getObject()) { session.run(); }` where appropriate. This serves as an orientation for the lesson on prototype cleanup, which explains callbacks and exception handling in detail.

## 17. When objects are created: how does eager/lazy apply to different scopes?

`ApplicationContext.refresh()` normally pre-instantiates **regular non-lazy singleton beans**. Prototypes are not bulk-instantiated when definitions are read, and request/session targets require an active web scope.

However, a dependency can pull in another object to be created when needed:

```text
Eager singleton Processor
   |
   +---- constructor requires prototype Worker
   |                    |
   |                    +--> Creates Worker when Processor is created
   |
   +---- provider<Worker>
                        |
                        +--> Does not create Worker until getObject()
```

Do not conclude "I put `@Lazy` on the bean so it won't be created at startup". An eager bean constructor-injecting that bean can still pull it up, even when the target is a lazy singleton.

### Bean scope is not creation order

Two independent singletons can be created in an order determined by the bootstrap mechanism. If A needs B, Spring resolves B along the dependency graph. `@Order` does not control singleton startup ordering; it is typically used to sort collection injections.

### @DependsOn and scope

`@DependsOn("x")` indicates that the dependent bean requires bean `x` to be initialized first; it neither changes `x`'s scope nor turns a prototype into a singleton. An eager bean with `dependsOn` can cause a lazy bean to be created early.

## 18. FactoryBean and bean scope: two layers of semantics

`FactoryBean<T>` is a Spring contract allowing a factory bean object to provide a product object. Do not confuse it with a `@Bean` factory method.

When a bean definition defines a `FactoryBean`:

- `BeanFactory` manages the **factory object** according to the definition's scope.
- `getBean("name")` typically returns the **product** created by the factory.
- `getBean("&name")` returns the **`FactoryBean` object**.
- `FactoryBean.isSingleton()` describes the product's singleton semantics from the factory.
- Product/caching/lifecycle also depend on the factory type, bean definition, implementation, and `BeanFactory`.

Therefore, you cannot simply look at `scope="singleton"` on a `FactoryBean` definition and conclude that every `getBean("name")` call is guaranteed to have the same product identity as a regular singleton bean. Examine **both the factory bean scope and the product semantics**.

This is an advanced topic; for an ordinary service class declared with `@Bean`, singleton/prototype still behave according to the rules in sections 4–8.

## 19. Custom scope: defining your own instance boundary

When the six standard scopes do not fit your domain, Spring lets you implement `org.springframework.beans.factory.config.Scope` and register it with `BeanFactory`.

The `Scope` interface has the following key contracts:

- `Object get(String name, ObjectFactory<?> objectFactory)`: find or create an object within the scope boundary.
- `Object remove(String name)`: remove an object from the scope.
- `void registerDestructionCallback(String name, Runnable callback)`.
- `Object resolveContextualObject(String key)`.
- `String getConversationId()`.

A custom scope must decide on **storage**, **isolation boundary**, **cleanup**, and **concurrency semantics**. For example, a tenant scope must ensure that tenant A's data never leaks into tenant B.

### 19.1. Registering a scope via API

```java
ConfigurableBeanFactory factory = ...;
factory.registerScope("tenant", tenantScope);
```

This is an illustrative snippet, requiring a `tenantScope` implementation of `Scope` and the proper `BeanFactory` configuration phase. With `ApplicationContext`, custom scopes are typically registered via `CustomScopeConfigurer` or an appropriate bootstrap configuration, **before** beans belonging to that scope need to be resolved.

### 19.2. Defining a scope in XML

```xml
<bean id="tenantWorkspace"
      class="example.TenantWorkspace"
      scope="tenant"/>
```

This will not work if the container has not registered a scope named `tenant`. Simply writing a new scope string in XML does not make Spring automatically know how to manage it.

### 19.3. Custom scope does not imply ThreadLocal safety

A tenant context stored in `ThreadLocal` can become stale/leak when thread pools reuse threads. With reactive processing or virtual threads, correlation and context propagation must also be designed properly. Do not write a simple custom scope storage backed by a global map keyed by a user string without addressing lifecycle, logout/eviction, concurrent access, and memory cleanup.

## 20. Bean aliases, multiple names, and scopes

A bean can have multiple names via aliases:

```xml
<bean id="catalogClient" class="example.CatalogClient"/>
<alias name="catalogClient" alias="legacyCatalogClient"/>
```

Both names map to the **same bean definition**; they do not automatically create two instances. If the definition is a singleton, typically:

```java
context.getBean("catalogClient")
        == context.getBean("legacyCatalogClient")
```

is true.

On the other hand, if you register **two separate bean definitions** with the same class but different names, they have separate scopes/lifecycles:

```java
@Bean("eastClient")
Client eastClient() {
    return new Client("east");
}

@Bean("westClient")
Client westClient() {
    return new Client("west");
}
```

Even if both are singletons, having the same class does not cause Spring to merge them into one object.

### Injection by type can be ambiguous

Two different `Client` bean definitions can cause `getBean(Client.class)` or constructor injection by type to suffer from ambiguity. Use `@Qualifier`, `@Primary`, or an explicit bean name. Scope is **not a criterion for selecting a single exact candidate** when multiple beans share the same type.

## 21. Inner bean definitions and scope

In Spring XML:

```xml
<bean id="processor" class="example.Processor">
    <constructor-arg>
        <bean class="example.Policy"/>
    </constructor-arg>
</bean>
```

The `example.Policy` bean inside the `<constructor-arg>` tag is an **inner bean definition**. It has no public top-level bean name for `getBean("policy")`. Inner beans are typically created as objects owned by the outer bean, and are not used as independent shared singletons.

If multiple consumers need the same policy singleton, register a separate named bean and use `ref`:

```xml
<bean id="policy" class="example.Policy"/>

<bean id="processor" class="example.Processor">
    <constructor-arg ref="policy"/>
</bean>
```

Do not misuse inner beans to build a "global singleton" just because the XML tag names look similar. Definition nesting and bean scope must be understood separately.

## 22. Web scope examples: contextualized illustrations

A singleton `RequestLoggingService` can inject a `RequestInfo` interface registered with `@Scope(value="request", proxyMode=ScopedProxyMode.INTERFACES)`. During an active HTTP request, two calls to `requestInfo.correlationId()` resolve the same request target; a different HTTP request resolves a different target. A plain `AnnotationConfigApplicationContext` in a CLI does not automatically have HTTP scopes. To run real examples and compare cookie/request/application state, see the dedicated lessons on web scopes, web-aware contexts, and annotations in the chapter.

## 23. Debugging scope-related issues

| Symptom | Common Cause | How to Handle |
| --- | --- | --- |
| Two `getBean()` calls for the same bean name return the same object | Singleton bean scope | Expected; check the definition's `scope` |
| Two `getBean()` calls for a prototype return two objects | Prototype semantics | Expected |
| Prototype injected into a singleton keeps getting reused | Dependency resolved only once when the singleton was created | Use `ObjectProvider`/factory per operation |
| Request bean used in CLI reports missing scope | No web-aware context | Use web scopes only in a web app, or custom mock/register the scope for tests |
| `Scope 'request' is not active` | No request bound to the thread/dispatch when the target is invoked | Place the lookup inside a valid active request |
| A session bean is mistakenly accessed across two users | Shared mutable target/wrong proxy/session binding | Fix scope ownership; do not cache the target in a singleton |
| Same scoped proxy reference but target ID changes | Proxy keeps its identity while target changes per request | This is expected behavior |
| Prototype scoped proxy state "disappears" between two methods | Each method invocation can hit a new target | Use a provider to fetch the target once |
| Scoped proxy fails with final class/method | Proxying limitations | Use an interface-based proxy or a provider |
| Prototype resource is not closed when context closes | Spring does not manage prototype destroy callbacks like singletons | Caller handles cleanup |
| Memory grows with the number of sessions | Session state too large/missing timeout/invalidation | Design cleanup; avoid retaining large objects |
| Singleton field contains the previous request's request ID | Per-request state stored in a long-lived bean | Pass as a method parameter or use request scope properly |
| One class but two singleton instances | Two bean definitions or two contexts | Check names/aliases/context boundaries |
| `@Lazy` singleton created later yet has the same identity | Lazy only changes timing, not scope | Expected |
| Prototype bean appears at startup | An eager singleton requires the prototype dependency | Inspect constructor/factory method parameters |
| Custom scope not found | Scope name not registered yet | `CustomScopeConfigurer`/`registerScope` before lookup |
| `NoUniqueBeanDefinitionException` | Multiple candidates of the same type | Qualifier/Primary/bean name |
| Direct call to `@Bean` method creates object outside `BeanFactory` | `proxyBeanMethods=false`/manual config instance | Use `BeanFactory` lookup/injection parameters |
| Confusing `FactoryBean` product identity | Factory vs. product scope semantics differ | Check `FactoryBean.isSingleton()` |
| Production-only bug with WebSocket session | Messaging infrastructure/scope lifecycle differs from tests | Test with a proper WebSocket/STOMP setup |

### Debugging Workflow

1. Verify the bean **name/alias** and the actual registered definition.
2. Look for `@Scope`/`@RequestScope`/`@SessionScope` or XML `scope="..."`.
3. Identify which **container** is creating the bean (parent, child, test context, app context).
4. Determine whether lookup uses `getBean`, constructor injection, provider, or scoped proxy.
5. If a singleton holds a prototype: check whether injection occurs **once** or via per-use lookup.
6. If a bean is web-scoped: verify that the request/session/WebSocket scope is active.
7. Separate the proxy's identity from the target instance.
8. Check scope-specific cleanup and object ownership.
9. Do not call `getBean` when you only want to check whether a bean has been created — lookup can trigger instantiation.
10. Test with the proper profile/web environment and concurrency/lifecycle where applicable.

## 24. Testing scope semantics

### 24.1. Testing singleton identity

```java
SharedCatalog a = context.getBean(SharedCatalog.class);
SharedCatalog b = context.getBean(SharedCatalog.class);
if (a != b) {
    throw new AssertionError("SharedCatalog is not singleton");
}
```

This is an additional snippet placed inside `main` of the section 8 project while `context` is open.

### 24.2. Testing prototype multiplicity

```java
TaskUnit first = context.getBean(TaskUnit.class);
TaskUnit second = context.getBean(TaskUnit.class);
if (first == second) {
    throw new AssertionError("Expected distinct prototype objects");
}
```

Do not assert literal IDs if other tests have already fetched prototypes earlier; verifying identity and the scope contract matters more than context-dependent sequence numbers.

### 24.3. Testing that a singleton holds a prototype once

```java
FixedConsumer fixed = context.getBean(FixedConsumer.class);
TaskUnit stored = fixed.taskUnit();

if (fixed.taskUnit() != stored) {
    throw new AssertionError("FixedConsumer changed its dependency");
}
```

The key point is that `FixedConsumer` retained the same reference. Whether it needs a new object each time is a **design requirement**, not a Spring bug.

### 24.4. Testing that a provider creates a prototype each time

```java
ObjectProvider<TaskUnit> units =
        context.getBeanProvider(TaskUnit.class);
TaskUnit a = units.getObject();
TaskUnit b = units.getObject();
if (a == b) {
    throw new AssertionError("Prototype provider returned same object");
}
```

### 24.5. Testing request scope must simulate HTTP lifecycle

With Spring's web test infrastructure, the mock request/session must be properly bound to `RequestContextHolder` or the corresponding mock web context when verifying target resolution. Creating a plain `AnnotationConfigApplicationContext` and calling `getBean` directly for a request-scoped target is not a genuine web integration test.

### 24.6. Testing cleanup

For a singleton with a `destroyMethod`, close the context and assert the appropriate callback. For a prototype, write a test proving that the application caller is responsible for closing it, rather than expecting the context cleanup to do so.

### 24.7. Testing scope via the BeanFactory API without creating the target

```java
String scope =
        context.getBeanFactory()
               .getBeanDefinition("taskUnit")
               .getScope();
```

With `@Scope("prototype")`, the scope string is `prototype`. For the default scope, the `BeanDefinition` scope field may not be explicitly recorded (an empty string represents the default singleton), so you need to understand the API contract; do not assert `getScope().equals("singleton")` for every default bean.

## 25. Frequently Asked Questions

### Is a singleton bean created strictly once across the entire JVM?

No. It is a singleton **per bean definition within each container**. Two independent contexts can have two instances. Two definitions of the same Java class in one context can also have two singleton instances.

### Does prototype mean a new bean per HTTP request?

No. It typically means a new bean **per instance request** from `BeanFactory`. If you want a bean that persists across lookups within one HTTP request, choose request scope.

### Is @Lazy a scope?

No. `@Lazy` adjusts **pre-instantiation timing**, not instance multiplicity. A lazy singleton still has only one managed singleton instance once created.

### Does bean scope change dependencies?

Scope determines when/how many objects are created from a bean definition. Dependency injection still needs to resolve the appropriate object; however, the timing and identity passed to the consumer are affected by scope.

### Why is a prototype created at startup despite not being bulk pre-instantiated?

Because an eager singleton can **require the prototype as a dependency**, leading to one instance being created right when the singleton is built.

### Does a singleton injecting a prototype automatically swap instances on each method run?

No. Constructor/property injection happens when the singleton is created, so the injected reference normally stays the same. Use a provider/factory/scoped proxy with the intended semantics if you need dynamic instances.

### Can @RequestScope be used in a console program?

Not automatically. It requires a web-aware context and an active request. A plain `ApplicationContext` normally does not have that scope, unless you intentionally register/mock the scope yourself for testing.

### Does a scoped proxy keep the same reference across multiple requests?

It can. The singleton consumer holds **the same proxy instance**, while the target resolved by the proxy per request/session can differ.

### Are a prototype scoped proxy and ObjectProvider the same?

No. A prototype scoped proxy can create a new target **on each method call**, whereas a provider lets you **explicitly obtain one target** via `getObject()` and use that same target throughout an operation.

### Are prototype beans automatically closed by Spring when the context closes?

Under normal Spring semantics, **no**. Spring invokes init callbacks but does not track and execute all prototype destruction callbacks; the caller must manage cleanup.

### Is application scope always the same as singleton?

No. Application scope is bound to the `ServletContext`; singleton is bound to a single Spring IoC container. When multiple contexts share one `ServletContext`, the difference can matter.

### Does Spring automatically register thread scope?

No. `SimpleThreadScope` exists, but it is **not registered by default**, and it has important lifecycle caveats.

### Is scope meant to guarantee thread safety?

No. Scope only specifies **sharing/lifespan**. Multiple threads can use the same singleton or session-scoped object, so mutable state still requires concurrency design.

### Are all objects created with `new` inside `@Bean` unmanaged by Spring?

The object **returned from a `@Bean` factory method invoked by the container** becomes a managed bean according to that definition. However, auxiliary objects created with `new` and kept internally without being returned or registered separately **do not automatically become Spring beans**. Clearly distinguish "factory method returns an object" from "manual `new` bypassing `BeanFactory`".

## 26. Exercises with Answers

### Exercise 1 — One definition, multiple objects

`TaskUnit` is declared with `@Bean @Scope("prototype")`. How many instances do two calls to `context.getBean(TaskUnit.class)` typically produce?

**Answer:** Two distinct instances from a single bean definition. Scope governs the creation/lookup mechanism, not definition duplication.

### Exercise 2 — Singleton per-container

Two independent `AnnotationConfigApplicationContext` instances both register `@Bean Cache cache()`. `Cache` is a singleton in each context. Are the two references guaranteed to be identical?

**Answer:** No. Each container manages its own singleton.

### Exercise 3 — Two bean names, same class

A configuration has `@Bean("a") Client clientA()` and `@Bean("b") Client clientB()`, both singletons. Is there exactly one `Client` instance in the container?

**Answer:** No. Two separate definitions can have two separate singleton objects.

### Exercise 4 — Lazy singleton

Is `@Bean @Lazy ExpensiveClient client()` a prototype?

**Answer:** No. By default it is still a singleton; `@Lazy` only changes when the container proactively creates it.

### Exercise 5 — Prototype injected into singleton

The eager singleton `BatchService` receives a prototype `TaskUnit` in its constructor. Does calling `batchService.process()` 10 times automatically receive 10 `TaskUnit` instances?

**Answer:** No. The constructor is called when the singleton is created and receives one prototype at that moment, then retains the reference.

### Exercise 6 — ObjectProvider

`BatchService` must create a new `TaskUnit` for each job. State how to solve this.

**Answer:** Inject `ObjectProvider<TaskUnit>` and in `processOneJob` call `getObject()` exactly once, using the returned `TaskUnit` for the entire job.

### Exercise 7 — Prototype scoped proxy

A workflow calls `proxy.prepare()` and then `proxy.commit()`. The proxy points to a prototype scope. Is the same target object guaranteed?

**Answer:** No. Each method call through a prototype scoped proxy can receive a new target. If shared state is needed, use a provider to fetch one instance first.

### Exercise 8 — Request scope

Two lookups of the same bean in one HTTP request, then two lookups in another HTTP request. How many request-scoped target objects are there normally?

**Answer:** One target per request, totaling two targets across the two requests, assuming the target is requested in both.

### Exercise 9 — Session scope

Two HTTP requests belonging to the same session use a session-scoped `CartState`. Do they typically obtain the same target?

**Answer:** Yes, within an active HTTP session according to the scope contract; a different session gets a separate target.

### Exercise 10 — Scope in CLI

A `@RequestScope` bean is looked up in a plain `AnnotationConfigApplicationContext` without a web request. Why can this fail?

**Answer:** Request scope is not registered/active; web scopes require a web-aware context and an active request lifecycle.

### Exercise 11 — Application scope

Spring has two child `WebApplicationContext` instances linked to the same `ServletContext`. Can there be an identity difference between `application` and `singleton` beans?

**Answer:** Yes. Application scope is per `ServletContext`; singleton is per container/definition. Check the hierarchy, bean names, and actual web infrastructure.

### Exercise 12 — Prototype lifecycle

`@Bean(destroyMethod="close") @Scope("prototype")` creates `TempBuffer`. When the context closes, is it guaranteed to call `close` on every buffer?

**Answer:** No, under the default prototype lifecycle; the client/owner is responsible for cleanup.

### Exercise 13 — Proxy and target

A singleton service holds a request-scoped proxy; two requests call the service. Can the proxy reference be the same while the targets differ?

**Answer:** Yes. The proxy reference is stable; the target is resolved according to each request's active scope.

### Exercise 14 — Custom scope

A developer writes `@Scope("tenant")` without registering a `Scope` implementation. Will it work?

**Answer:** No, when a tenant bean is requested; the `tenant` scope must be registered before lookup.

### Exercise 15 — Thread safety

A singleton has `int count` and executes `count++` across 100 concurrent requests. Does the singleton scope automatically guarantee the correct result?

**Answer:** No. You need thread-safe mutable state or a stateless design.

### Exercise 16 — Alias

`<bean id="reportClient".../>` has `<alias name="reportClient" alias="oldReportClient"/>`. Do the two names create two singleton objects?

**Answer:** No. The alias points to the same bean identity.

### Exercise 17 — Prototype vs. request

You want a single `RequestContext` per HTTP request regardless of how many times code looks it up. Choose `prototype` or `request`?

**Answer:** Choose request scope. Prototype creates a new instance on every bean lookup and does not keep a single target for the entire HTTP request.

### Exercise 18 — Scope and order

`@Order(1)` on singleton A, `@Order(2)` on singleton B. Does this specify that object A is created before B?

**Answer:** No. `@Order` typically affects ordering of collections/candidates, not singleton creation order.

### Exercise 19 — Program output

In the section 8 demo, why is `fixedTaskId=1` while `directPrototypeIds=2,3`?

**Answer:** The eager `FixedConsumer` was injected with the first prototype during startup; the `getBean` calls in `main` created the next two instances.

### Exercise 20 — Dynamic IDs

Why do two calls to `dynamic.newTaskId()` produce IDs 4 and 5?

**Answer:** The consumer holds a provider rather than a concrete `TaskUnit`; each `getObject()` creates a new prototype using the same singleton `Sequence` counter.

### Exercise 21 — Lazy marker

`RareTool` is annotated with `@Lazy` and no eager bean requires it. What is `marker.created()` right after refresh?

**Answer:** False. After the first `getBean(RareTool.class)`, the constructor marks it true; the second lookup returns the same singleton.

### Exercise 22 — Scope leak

A singleton directly retains a `UserPreferences` session target from Alice's request, then handles Bob's request. What is the risk?

**Answer:** Reusing wrong/stale state across sessions, or even leaking data. Inject a scoped proxy/provider or pass request/session data with proper boundaries; never cache the target.

## 27. Practice Checklist

- [ ] Distinguished bean definition from object instance.
- [ ] Understood that each bean definition has its own scope.
- [ ] Understood that singleton is **per bean/per container**.
- [ ] Did not confuse singleton with a static/global GoF Singleton.
- [ ] Did not treat singleton as thread-safe by default.
- [ ] Prototype creates a new object on each bean lookup.
- [ ] Did not confuse prototype with per HTTP request.
- [ ] Knew that a singleton injects a prototype **only once** at creation/injection time.
- [ ] Used `ObjectProvider`/factory when a prototype is needed per operation.
- [ ] If using a prototype scoped proxy, verified per-method-call semantics.
- [ ] Distinguished `@Lazy` timing from `@Scope` multiplicity.
- [ ] Understood that an eager bean can trigger early creation of a lazy dependency.
- [ ] Used the proper web-aware context for request/session/application/websocket scopes.
- [ ] Did not look up a request-scoped target outside an active request.
- [ ] Did not store a concrete short-lived target in a long-lived singleton.
- [ ] Matched scoped proxy mode to interface/class, avoiding `final` proxy limitations.
- [ ] Did not store mutable request/session data in singleton fields.
- [ ] Ensured session state has lifecycle, timeout, size, and concurrency controls.
- [ ] Did not confuse application-scoped objects with per-context singletons.
- [ ] Ensured custom scopes have clear storage, conversation key, destruction, and cleanup.
- [ ] Did not assume thread scope is automatically available.
- [ ] Ensured prototype resources are cleaned up by the caller/owner.
- [ ] Did not use direct `new` expecting Spring scope/lifecycle management.
- [ ] Did not directly call `@Bean` methods in lite configuration to obtain managed objects.
- [ ] Clearly distinguished bean aliases and multiple bean definitions.
- [ ] Tested identity, scope cardinality, first use, web scopes, and cleanup.
- [ ] If using `FactoryBean`, distinguished factory vs. product scope.
- [ ] Did not use scope as a "workaround" for a dependency cycle or improper business ownership.

## Summary

**Scope determines the relationship between a bean definition and its instances**: the same metadata recipe can be bound to **one managed singleton object**, create **multiple prototype instances**, or return a target managed per **HTTP request, session, `ServletContext`, WebSocket session, or custom boundary**.

Four things to remember:

1. **Spring singleton = one managed object per bean definition in one IoC container**, not a single object across every class/global JVM.
2. **Prototype = creates a new instance per bean lookup**, yet a singleton directly injecting a prototype **receives only one instance when the dependency is resolved**.
3. **Web scopes = target changes per active web lifecycle**; use a scoped proxy, provider, or method parameters for short-lived dependencies in long-lived consumers.
4. **Lifecycle is tied to scope**: Spring manages singleton destruction with the context, whereas for prototypes the caller typically handles cleanup; `@Lazy` does not alter these semantics.

When designing, choose scope based on the object's **ownership, lifespan, sharing, and concurrency**; choose the injection mechanism based on **when the collaborator is needed**; and verify with context tests rather than guessing from a Java class name or a single annotation.

## Official References

- [Spring Framework 6.2 — Bean Scopes](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html): six standard scopes, singleton/prototype, scoped proxy, web scopes, custom scope, and lifecycle.
- [Spring Framework 6.2 — Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-lazy-init.html): how bean scope differs from eager/lazy behavior.
- [Spring Framework 6.2 — Dependency Injection](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-collaborators.html): constructor/property wiring and the dependency graph.
- [Spring Framework 6.2 — Method Injection](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-method-injection.html): `@Lookup`, prototype in singleton, and lookup injection limitations.
- [Spring Framework 6.2 — @Scope API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/Scope.html): scope names and `ScopedProxyMode`.
- [Spring Framework 6.2 — ObjectProvider API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/ObjectProvider.html): deferred/dynamic bean lookup.
- [Spring Framework 6.2 — Scope SPI](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/config/Scope.html): custom scope contract.
