# Singleton Per Bean and Per Container in the Spring Framework Core Container

## 1. Short answer: one bean definition, one container, one managed singleton

In the Spring Framework, `singleton` is the default scope. When a **bean definition** is marked as singleton, the Spring IoC Container manages one shared instance of that bean within **the scope of the container owning the bean**. Subsequent requests for the same bean name (or an alias of that bean name) in the same container typically return the same managed object reference.

More precisely:

> **Spring singleton = one shared instance per singleton bean definition per Spring IoC container.**

This definition has two independent axes:

- **Per bean:** two different bean definitions, even of the same Java class, can still produce **two different singleton objects** in the same container.
- **Per container:** two independent Spring `ApplicationContext` instances, even if they load the same `@Configuration` class and use the same bean name, typically manage **two different singleton instances**.

This rule differs completely from the Gang of Four (GoF) Singleton pattern, which usually enforces a single instance at the class/ClassLoader level via a static field or private constructor. A Spring singleton **does not automatically turn a Java class into a global singleton**.

Example:

```java
@Configuration(proxyBeanMethods = false)
class RepositoryConfig {

    @Bean("mainRepository")
    Repository mainRepository() {
        return new Repository("main");
    }

    @Bean("archiveRepository")
    Repository archiveRepository() {
        return new Repository("archive");
    }
}
```

This is an **illustrative snippet**; it requires Spring imports and the `Repository` class. Although both `@Bean` methods return **the same `Repository` class**, they declare **two beans with different names**, so by default each definition has its own singleton instance within a context.

Suppose `context` loads `RepositoryConfig`:

```java
Object first = context.getBean("mainRepository");
Object second = context.getBean("mainRepository");
Object archive = context.getBean("archiveRepository");

System.out.println(first == second);    // true
System.out.println(first == archive);   // false
```

This is an illustrative snippet assuming both factory methods actually construct new objects, rather than a class returning the same static object. The `==` operator compares **reference identity**, which is the exact check needed to distinguish singleton scope from two separate beans.

This lesson answers:

1. Does "singleton" in Spring belong to a **class**, a **bean name**, or an **`ApplicationContext`**?
2. Do two `@Bean` methods with the same return type share a singleton?
3. Does a bean with another alias create a second object?
4. Do two `ApplicationContext` instances loading the same configuration share an instance?
5. Why do multiple controllers/services injecting one bean hold the same shared reference?
6. How does `scope="singleton"` differ from `prototype`, `request`, and `session`?
7. How do the singleton cache, lifecycle, lazy initialization, `FactoryBean`, and proxies affect identity?
8. What does the container guarantee regarding thread-safety, and what state must developers protect themselves?
9. How do you verify this using Java 17+ and Spring Framework 6.2 without relying on console hash codes?

## 2. Visual model: identification by bean and container

Suppose the same `ReportStore` class is declared twice in Context A, and once in Context B:

```text
                   ApplicationContext A
     +-------------------------------------------+
     | BeanDefinition "primaryStore"  [singleton] |
     |               |                           |
     |               v                           |
     |         ReportStore object #A1             |
     |               ^                           |
     |    getBean("primaryStore") multiple times  |
     |                                           |
     | BeanDefinition "backupStore"   [singleton] |
     |               |                           |
     |               v                           |
     |         ReportStore object #A2             |
     +-------------------------------------------+

                   ApplicationContext B
     +-------------------------------------------+
     | BeanDefinition "primaryStore"  [singleton] |
     |               |                           |
     |               v                           |
     |         ReportStore object #B1             |
     +-------------------------------------------+
```

Expected identities when each context's factory creates new objects:

- A: repeated `getBean("primaryStore")` → object #A1.
- A: `getBean("backupStore")` → object #A2, distinct from #A1.
- B: `getBean("primaryStore")` → object #B1, distinct from #A1.
- The Java class of #A1, #A2, and #B1 **can be identical**.

Therefore, saying "Spring creates only one `ReportStore` for the entire application" is an unqualified statement. If the application has multiple bean definitions or multiple containers, it can legitimately have multiple `ReportStore` instances.

### 2.1. "One bean" is a container metadata concept

A Spring bean is identified in the registry by its **bean definition/registration along with its name** and scope. The Java class is only one piece of metadata. Other attributes can include:

| Attribute | Example | Role |
| --- | --- | --- |
| Bean name | `primaryStore` | Lookup/DI by name |
| Alias | `storeForBilling` | Another name for the same bean |
| Factory/class | `ReportStore` or `@Bean` method | How Spring creates the bean |
| Scope | `singleton` | Object reuse policy |
| Constructor arguments | Repository/URL/config | Information for creating the object |
| Dependencies | `ref`/`@Qualifier`/method parameter | Relationships among managed beans |
| Lazy | `@Lazy` | Creation timing |
| Lifecycle | init/destroy callbacks | Object management cycle |
| Candidate metadata | `@Primary`/qualifiers | Bean selection during by-type injection |

Two beans with the same class but different names/configs are not two aliases of one bean. Conversely, one bean with multiple aliases is still **one managed bean**.

### 2.2. Singleton does not mean the bean is created before everything else

Singleton describes **the number of managed/reused instances**, not the creation time. In an `ApplicationContext`, default singletons are normally eagerly pre-instantiated during refresh. However, `@Lazy` can defer bean creation until requested, provided no eager dependency pulls it in early.

A singleton may not yet exist as an instance while its **bean definition already exists** in the registry. `containsBean("x")` and `containsSingleton("x")` are not the same test.

## 3. Comparison with the GoF Singleton pattern

A Spring singleton is **per bean registration and per container**; the classic GoF Singleton manages an instance via a static holder/restricted constructor at the Java class/ClassLoader level. A Spring `@Bean` with a public constructor can still be a singleton, whereas a GoF instance might be returned by a factory to be shared across multiple containers. Using a static global instance makes test isolation or resource ownership harder. The lesson "Distinguishing Spring Singleton from the GoF Singleton Pattern" analyzes the mechanism thoroughly, providing holder examples and comparative output.

## 4. Singleton default in XML and JavaConfig

### 4.1. XML

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="mainStore" class="demo.Store"/>

    <bean id="backupStore"
          class="demo.Store"
          scope="singleton"/>

</beans>
```

This is an illustrative XML configuration; the class `demo.Store` must exist. The two bean definitions have two different names. `scope="singleton"` on the second bean merely states explicitly what is already the default policy.

### 4.2. JavaConfig

```java
@Configuration(proxyBeanMethods = false)
class StoreConfig {

    @Bean("mainStore")
    Store mainStore() {
        return new Store("main");
    }

    @Bean("backupStore")
    @Scope("singleton")
    Store backupStore() {
        return new Store("backup");
    }
}
```

This illustrative snippet requires imports and the `Store` class. The `@Scope("singleton")` annotation on the second bean is for illustration, as the default scope is singleton.

For a `@Bean` method:
- The default bean name is the **method name**, if `@Bean("name")` is not specified.
- A singleton bean is normally created once by the container and then stored for reuse by subsequent requests.
- Spring may insert `BeanPostProcessor`s, AOP proxies, and lifecycle behavior around bean creation; the object returned from `getBean` can be a managed proxy, not necessarily the raw object created with `new` inside the method body.
- Direct Java calls to a factory method outside `BeanFactory` have their own semantics and are not automatically bean lookups in every configuration.

### 4.3. Component scanning

A class:

```java
@Component
public class CatalogService {
}
```

is normally scanned into one bean definition (bean name according to the naming strategy, e.g., `catalogService`) with the default singleton scope.

However, the same class can be declared with **an additional definition** via `@Bean` or programmatic registration under a different name. There is no rule saying "each `@Component` class has only one bean across the entire system"; the actual number of definitions is determined by registration sources and collision rules.

Be careful to control duplicate scanning or parallel registrations. If names collide, Spring may reject or override depending on the registry policy; if names differ, you may end up with two candidates of the same type and cause ambiguity for by-type injection.

## 5. Two bean definitions of the same class in one container

Example:

```java
@Bean("primaryClient")
HttpClient primaryClient() {
    return new HttpClient("primary");
}

@Bean("auditClient")
HttpClient auditClient() {
    return new HttpClient("audit");
}
```

This is a non-standalone snippet; the `HttpClient` class is an illustrative domain type rather than `java.net.http.HttpClient`. Within the same context and two default singleton definitions:

```java
Object p1 = context.getBean("primaryClient");
Object p2 = context.getBean("primaryClient");
Object audit = context.getBean("auditClient");

boolean samePrimary = p1 == p2; // true
boolean differentBeans = p1 != audit; // true
```

### 5.1. Two beans of the same class need not have the same state

`primaryClient` can be configured with a different timeout from `auditClient`; the same Java class does not imply identical behavior:

```xml
<bean id="primaryClient" class="demo.Client">
    <property name="region" value="north"/>
</bean>

<bean id="auditClient" class="demo.Client">
    <property name="region" value="south"/>
</bean>
```

Each definition has its own metadata. The singleton for `primaryClient` cannot be inferred to also be the singleton for `auditClient`.

### 5.2. By-type injection can become ambiguous

When there are two beans of type `Client`:

```java
@Bean
ReportService reportService(Client client) {
    return new ReportService(client);
}
```

there may no longer be a single unique candidate. Without an appropriate primary/qualifier/selection rule, Spring can throw `NoUniqueBeanDefinitionException` or a bean-creation-related exception.

Solutions:
- `@Qualifier("primaryClient") Client client` in the method parameter or constructor.
- `@Primary` on the default bean if that fits the design.
- Use `List<Client>` when the consumer genuinely needs all candidates.
- Do not use `@Order` to "auto-select" a singleton for a single-value injection; collection ordering and candidate selection are two separate concerns.

### 5.3. Checking counts by name, not just by class

`context.getBeansOfType(Client.class)` can return a mapping of bean names to objects of the same type. However, the number of entries does not always equal the number of physical objects if there are aliases, `FactoryBean`s, or factories intentionally returning the same reference. Therefore combine:
- the list of names and definitions;
- `isSingleton("name")`;
- `==` comparison on references;
- tests of behavior and proxy semantics.

## 6. Aliases: multiple names do not create multiple singletons

Spring allows one definition to have multiple names.

XML:

```xml
<bean id="primaryStore" class="demo.Store"/>
<alias name="primaryStore" alias="billingStore"/>
<alias name="primaryStore" alias="shippingStore"/>
```

Corresponding JavaConfig:

```java
@Bean(name = {
        "primaryStore", "billingStore", "shippingStore"
})
Store primaryStore() {
    return new Store("primary");
}
```

These fragments require the appropriate root/imports/classes. All three names here point to **one bean definition**. For a singleton:

```java
Object primary = context.getBean("primaryStore");
Object billing = context.getBean("billingStore");
Object shipping = context.getBean("shippingStore");

boolean same = primary == billing && billing == shipping;
```

`same` is true if the names are valid aliases of the singleton bean. Use aliases for legacy naming compatibility or sharing names across modules; do not create multiple `@Bean` methods just to simulate aliases.

### 6.1. An alias is not a second bean

Some developers print `getBeanDefinitionNames()` and conclude that an alias is "missing" because the second name does not appear in the definitions list. That is normal: the alias registry and the bean definition registry have separate semantics.

To verify:
- `context.containsBean("billingStore")` can return true.
- `context.getAliases("primaryStore")` returns the registered alias names.
- `getBean("billingStore") == getBean("primaryStore")` proves reference identity.

### 6.2. An alias is not `@Primary` or an automatic qualifier

An alias is simply another name. It does not force Spring to choose that bean when multiple beans of the same type exist. If a single dependency is ambiguous, use a qualifier, `@Primary`, or an explicit named lookup intentionally.

## 7. Multiple consumers injecting the same singleton

A common scenario:

```text
       Bean "sharedRepository" (singleton)
                  |
       +----------+----------+
       |                     |
       v                     v
 ServiceA.repository    ServiceB.repository
       |                     |
       +------ same object --+
```

JavaConfig:

```java
@Bean("sharedRepository")
Repository sharedRepository() {
    return new Repository();
}

@Bean("serviceA")
ServiceA serviceA(Repository repository) {
    return new ServiceA(repository);
}

@Bean("serviceB")
ServiceB serviceB(Repository repository) {
    return new ServiceB(repository);
}
```

This is an illustrative snippet; to guarantee the right selection if there are multiple repositories, add `@Qualifier("sharedRepository")`.

Spring resolves the bean dependency and supplies the same singleton reference to consumers within **the same container**. In practice, in a system with AOP, the reference can be **the same proxy** representing the managed bean; what matters is that consumers receive the same Spring-managed reference rather than creating another object with `new`.

### 7.1. Consumer fields are not two copies

If `ServiceA` holds `repository` and `ServiceB` holds `repository`, those are simply two Java references pointing to the same object. Calling a method on one reference can mutate runtime state observed through the other reference if the repository is mutable.

This sharing is useful for:
- stateless service beans;
- a shared connection pool manager;
- a singleton cache;
- a configuration registry;
- immutable lookup tables;
- managed cross-cutting infrastructure.

However, it also introduces risks if the bean stores state specific to each request or user.

### 7.2. Singleton does not mean an object is created per method call

A singleton controller receiving a singleton service does not create a new service when each request arrives. A singleton's constructor/factory method normally runs once **when the bean is created**. Business method calls on the existing object can run very many times and can run concurrently.

If a singleton method needs a new object per invocation, design its creation separately: a local `new` object without the container, `ObjectProvider<PrototypeBean>`, a factory abstraction, or an appropriate scoped object.

## 8. Each `ApplicationContext` typically has its own singleton cache

In a Java application, you can create:

```java
var first =
        new AnnotationConfigApplicationContext(MyConfig.class);
var second =
        new AnnotationConfigApplicationContext(MyConfig.class);
```

This is an illustrative snippet, requiring imports/class `MyConfig`. The two `AnnotationConfigApplicationContext` instances are **two independent IoC containers**. Each context registers bean definitions from `MyConfig` and instantiates/caches its own beans.

With the factory method:

```java
@Bean
Widget widget() {
    return new Widget();
}
```

typically:

```java
Object left = first.getBean("widget");
Object right = second.getBean("widget");

boolean different = left != right; // true
```

**Do not assert "it is true that because they share a classloader they will share an instance".** Sharing a classloader only affects class/static metadata; Spring's singleton cache remains per container.

### 8.1. Test context caching is an exception when "counting contexts"

The Spring TestContext Framework can **cache/reuse the same `ApplicationContext`** across multiple test cases when the context configuration is deemed compatible. Therefore, two test methods using `@SpringJUnitConfig` do not necessarily create two separate containers automatically.

When you need a fresh context for test isolation, design separate test fixtures or use `@DirtiesContext` in the right situations; do not guess "each test class = a new context". This is a difference in test framework reuse, not a violation of singleton scope.

### 8.2. Spring Boot is not implicitly one JVM-wide singleton

A Spring Boot application run normally has one main root application context, yet there can be multiple contexts depending on test setup, parent-child integration, management contexts, or multiple embedded applications in one JVM. Singleton beans do not automatically cross context boundaries.

### 8.3. Parent-child context hierarchy

With a parent/child context:
- A child can look up a bean in the parent when there is no local bean of the same name and parent visibility permits it.
- If the child retrieves a parent bean via delegation, the returned reference can be **the exact singleton owned by the parent**.
- A child can register a local bean with the same name, shadowing the parent bean during lookups from the child.
- Each context still retains its own singleton cache/ownership; delegation does not mean caches are "merged" into one global cache.

Thus the accurate statement is not "any two contexts must return different objects", but rather **a singleton belongs to the container that owns its bean definition**. If the child returns a parent bean, it is returning the instance **managed by the parent**; if two contexts register independent definitions, each typically creates its own instance.

### 8.4. A factory returning a static instance can be shared by two contexts

Example:

```java
final class GlobalClient {
    static final GlobalClient INSTANCE = new GlobalClient();

    private GlobalClient() {
    }
}

@Configuration(proxyBeanMethods = false)
class SharedConfig {
    @Bean("client")
    GlobalClient client() {
        return GlobalClient.INSTANCE;
    }
}
```

The code above illustrates an intentional static instance. Two contexts using `SharedConfig` will receive **the same Java object** if the ClassLoader/class identity is also shared.

This **does not erase the per-container definition**: each context still has its own singleton registration/cache entry, yet both factory methods return the same pre-existing reference. That is a result of **user factory code**, not Spring inventing a global singleton.

**Risk:** if the same resource instance is treated as owned by multiple contexts and both register destroy callbacks, the object may be closed multiple times. Avoid sharing static resources across containers when lifecycle ownership is unclear.

## 9. Singleton cache and lifecycle

### 9.1. Bean definition differs from bean instance

Spring holds metadata for a bean name before the object is created. The singleton instance is stored in the container after Spring handles creation/initialization according to the lifecycle. At a conceptual level:

```text
BeanDefinition("catalogService", scope=singleton)
                      |
                      v
         BeanFactory has instance?
                 /          \
             not yet        yes
                |            |
        create/configure     |
            object           |
                |            |
             cache ----------+
                |
                v
        getBean("catalogService")
         returns managed reference
```

Spring's actual implementation also has caches/early singleton references/factory handling to support complex situations such as circular dependencies, AOP, and singleton registration. This simple diagram is **not** a complete description of every internal map/lock.

### 9.2. Eager singleton is the default in `ApplicationContext`

Non-lazy singletons are normally created when context refresh completes. This enables fail-fast behavior if:
- a constructor throws an exception;
- dependencies do not exist;
- an init callback fails;
- configuration metadata is invalid.

Using `@Lazy` on a bean definition:

```java
@Bean
@Lazy
ExpensiveClient expensiveClient() {
    return new ExpensiveClient();
}
```

can defer bean creation until needed. However, if an eager singleton consumer injects this dependency directly, Spring still must create it to satisfy the dependency. Lazy does not change "one singleton per bean definition"; it only changes the **creation point**.

### 9.3. `containsSingleton` and `isSingleton` do not have the same meaning

Spring's `BeanFactory`/registry provides different checks:

| API | Approximate Meaning |
| --- | --- |
| `containsBean("x")` | A bean with that name/alias can be found in the appropriate factory/hierarchy |
| `containsBeanDefinition("x")` | There is a **local bean definition** named `x` in the registry |
| `containsSingleton("x")` | There is a singleton instance registered/cached in the local singleton registry |
| `isSingleton("x")` | The bean is treated as a singleton upon lookup per the `BeanFactory` contract |
| `isPrototype("x")` | The bean is treated as a prototype per the `BeanFactory` contract |
| `getBean("x")` | Requests an instance; can trigger bean creation |

In particular, a `@Lazy` singleton bean can have `containsSingleton("x") == false` before lookup yet `isSingleton("x") == true`. Do not deduce that "not yet cached" means "prototype scope".

`FactoryBean`s and scoped proxies can make the `isSingleton(name)` question more complex; read the API contract and know whether you are asking about the **factory** or the **product**.

### 9.4. When the context closes

A properly closed `ConfigurableApplicationContext` runs appropriate destroy callbacks for managed singleton beans. A bean definition does not necessarily live forever in the JVM, and Spring does not guarantee that a managed reference remains usable after the context has closed.

With JavaConfig:

```java
@Bean(name = "resource", destroyMethod = "close")
ManagedResource resource() {
    return new ManagedResource();
}
```

The container invokes `close` per lifecycle when the context closes normally.

Spring also has **destroy method inference** on `@Bean` if the class has a public no-argument `close` or `shutdown` method; when you do not want that callback inferred, `@Bean(destroyMethod="")` can disable the inference portion, though it does not disable all lifecycle contracts such as `DisposableBean`.

### 9.5. Do not use `System.identityHashCode` as sole proof

`System.identityHashCode(obj)` gives a useful number for debugging, yet **two different objects can collide on the same identity hash code**. Check identity with `==`. If you need deterministic stdout output, print booleans from comparisons rather than relying on addresses/hashes that vary across runs.

## 10. Singleton does not automatically guarantee thread-safe state

Spring safely publishes initialized singletons through the container according to lifecycle rules, yet every thread calling business methods on the same singleton can still contend over mutable state. For example, `private int hits;` and `++hits` are not atomic, losing updates under concurrent calls. Prefer **stateless** singleton services, keeping per-request data in method parameters/local variables; when a shared counter is needed, use `AtomicInteger` or appropriate locking.

`final` only keeps the reference stable; a mutable dependency inside does not automatically become thread-safe. `volatile` does not make `count++` atomic. The lesson "Shared State and Thread Safety of Singletons" dives deeply into the Java Memory Model, immutable snapshots, `Atomic*`, concurrent collections, and race testing.

## 11. Comparing singleton with other scopes

`singleton` reuses one managed instance per bean/container; `prototype` creates a bean each time the container resolves it; `request` and `session` bind to an HTTP request/session in a web context; `application` binds to the `ServletContext`; `websocket` binds to a STOMP session. Web scopes require supporting infrastructure; Spring does not automatically destroy prototypes when the context closes.

If a singleton directly constructor-injects a prototype, the prototype instance is retained at injection time; use `ObjectProvider<T>` when a new instance is needed per operation. If injecting a request bean, use a scoped proxy or provider within an active request. Remember that a proxy reference can be a singleton even while the target changes by scope.

## 12. Java configuration and calling a `@Bean` method directly

One of the common misconceptions is: "A `@Bean` method runs only once, so calling that method directly always gives the singleton."

You must distinguish between two modes.

### 12.1. Full `@Configuration(proxyBeanMethods=true)`

In the default full configuration mode, Spring can enhance the configuration class with CGLIB. Inter-bean method calls on the managed configuration instance can be intercepted to return the scoped bean from the container.

```java
@Configuration
class FullConfig {

    @Bean
    Repository repository() {
        return new Repository();
    }

    @Bean
    Service service() {
        return new Service(repository());
    }
}
```

This is an illustrative snippet. In full mode, the call to `repository()` from `service()` can go through Spring inter-bean interception and receive the managed singleton object.

### 12.2. `@Configuration(proxyBeanMethods=false)`

In lite/non-intercepted mode:

```java
@Configuration(proxyBeanMethods = false)
class LiteConfig {

    @Bean
    Repository repository() {
        return new Repository();
    }

    @Bean
    Service service() {
        return new Service(repository());
    }
}
```

The `repository()` call inside `service()` is a **normal Java method call**, which can create a second raw `Repository`, not the managed singleton `repository` registered by `BeanFactory`.

Better configuration:

```java
@Bean
Service service(Repository repository) {
    return new Service(repository);
}
```

Factory-method parameter injection ensures `BeanFactory` supplies the managed dependency and does not rely on inter-bean CGLIB interception.

### 12.3. Calling a method on a config object created with `new`

```java
LiteConfig config = new LiteConfig();
Repository raw = config.repository();
```

This is not `context.getBean("repository")`. The `@Bean` annotation only has Spring semantics when the definition is registered/processed in the context; directly calling a method on a manually instantiated object is ordinary Java code.

Verify identity through the managed API rather than looking at a method annotated with `@Bean` and assuming manual calls are singleton-cached.

## 13. FactoryBean, aliases, and advanced singleton semantics

`FactoryBean<T>` differs from a `@Bean` factory method:

- A bean definition can register a **factory object** implementing `FactoryBean<T>`.
- `getBean("name")` typically requests the **product** supplied by the factory.
- `getBean("&name")` requests the **factory bean instance**.
- `FactoryBean#isSingleton()` governs product object semantics and caching per the factory contract; it is not automatically synonymous with the scope of the bean definition holding the factory.

Conceptual example:

```java
FactoryBean<?> factory =
        (FactoryBean<?>) context.getBean("&clientFactory");

Object product = context.getBean("clientFactory");
```

This requires a bean named `clientFactory` that actually implements `FactoryBean`. The two references normally belong to **two different object layers**: factory and product.

A singleton factory can produce non-singleton products, depending on `isSingleton()`. Conversely, singleton products are cached per the product contract. Therefore **do not call `isSingleton("name")` blindly** and assume you have checked the same layer; examine `FactoryBean` API semantics whenever product/factory indirection exists.

### 13.1. A bean name can return an AOP proxy

A singleton bean wrapped by AOP post-processors can cause `getBean("service")` to return a proxy. Comparing `==` multiple times on the same name still shows the managed singleton reference is reused, yet the raw target and the proxy are not the same Java object.

This does not turn the singleton into a prototype. The container manages an **exposed singleton reference** for that bean, which may be a proxy. When testing identity, compare **consumer-visible references**, rather than constructing a raw target object yourself and expecting `==` against the proxy.

### 13.2. Bean definitions can be replaced/overridden

In containers/bootstraps that allow bean definition overriding, the same bean name can be re-registered in a controlled way. This is not behavior you should rely on to share singletons across modules. Especially in tests using `@MockitoBean` or `@TestBean`, the observed instance may be replaced/wrapped by test infrastructure.

Always identify the **actual runtime context and bean definition** under test, rather than just reading a single `@Configuration` file.

## 14. Runnable Java 17+ Example: bean identity and context ownership

The demo directly proves:
- Within one context, two `getBean("primaryRepo")` calls return the same object.
- `repoAlias` points to the same bean as `primaryRepo`.
- Two `@Bean` definitions return the same `NamedRepository` class yet hold two separate objects.
- Two consumers both injecting the managed primary repository share the same instance.
- Two contexts loading the same `DemoConfig` have separate primary repositories when each factory call creates an object with `new`.
- A prototype bean returns a new instance on each lookup.
- Manually calling `new NamedRepository` is not a container-managed bean lookup.
- Resource singletons have independent lifecycles per context: closing the first context does not close the resource belonging to the second context.

**Project:** Spring Context 6.2.19, Java 17+, Gradle, no Spring Boot or database.

### 14.1. Directory structure

```text
spring-singleton-boundaries/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── demo/
                └── SingletonBoundariesDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'spring-singleton-boundaries'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

application {
    mainClass = 'demo.SingletonBoundariesDemo'
}
```

Spring `spring-context` pulls in the required Spring Beans/Core modules; the code does not use web scopes. Use a Gradle version compatible with your JDK 17+.

### 14.2. Full Java source

Save `src/main/java/demo/SingletonBoundariesDemo.java`:

```java
package demo;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;

public final class SingletonBoundariesDemo {

    public static final class NamedRepository {
        private final String name;

        public NamedRepository(String name) {
            this.name = name;
        }

        public String name() {
            return name;
        }
    }

    public static final class CatalogService {
        private final NamedRepository repository;

        public CatalogService(NamedRepository repository) {
            this.repository = repository;
        }

        public NamedRepository repository() {
            return repository;
        }
    }

    public static final class Ticket {
        public Ticket() {
        }
    }

    public static final class ManagedResource {
        private boolean closed;

        public void close() {
            closed = true;
        }

        public boolean isClosed() {
            return closed;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class DemoConfig {

        @Bean(name = {"primaryRepo", "repoAlias"})
        public NamedRepository primaryRepo() {
            return new NamedRepository("primary");
        }

        @Bean("archiveRepo")
        public NamedRepository archiveRepo() {
            return new NamedRepository("archive");
        }

        @Bean("catalogService")
        public CatalogService catalogService(
                @Qualifier("primaryRepo")
                NamedRepository repository) {
            return new CatalogService(repository);
        }

        @Bean("auditService")
        public CatalogService auditService(
                @Qualifier("primaryRepo")
                NamedRepository repository) {
            return new CatalogService(repository);
        }

        @Bean("ticket")
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        public Ticket ticket() {
            return new Ticket();
        }

        @Bean(name = "managedResource",
              destroyMethod = "close")
        public ManagedResource managedResource() {
            return new ManagedResource();
        }
    }

    private static void verify(boolean condition,
                               String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        ManagedResource firstResource;
        ManagedResource secondResource;

        try (var second = new AnnotationConfigApplicationContext(
                DemoConfig.class)) {

            secondResource = second.getBean(
                    "managedResource", ManagedResource.class);

            try (var first =
                    new AnnotationConfigApplicationContext(
                            DemoConfig.class)) {

                NamedRepository primary1 = first.getBean(
                        "primaryRepo", NamedRepository.class);
                NamedRepository again = first.getBean(
                        "primaryRepo", NamedRepository.class);
                NamedRepository byAlias = first.getBean(
                        "repoAlias", NamedRepository.class);
                NamedRepository archive = first.getBean(
                        "archiveRepo", NamedRepository.class);
                NamedRepository primary2 = second.getBean(
                        "primaryRepo", NamedRepository.class);

                CatalogService catalog = first.getBean(
                        "catalogService", CatalogService.class);
                CatalogService audit = first.getBean(
                        "auditService", CatalogService.class);

                Object ticket1 = first.getBean("ticket");
                Object ticket2 = first.getBean("ticket");
                NamedRepository outside =
                        new NamedRepository("manual");

                firstResource = first.getBean(
                        "managedResource", ManagedResource.class);

                boolean repeatedSame = primary1 == again;
                boolean aliasSame = primary1 == byAlias;
                boolean definitionsDistinct = primary1 != archive;
                boolean sameClass =
                        primary1.getClass() == archive.getClass();
                boolean consumersShare =
                        catalog.repository() == audit.repository()
                        && catalog.repository() == primary1;
                boolean separateContexts = primary1 != primary2;
                boolean prototypeDistinct = ticket1 != ticket2;
                boolean manualOutside = outside != primary1;
                boolean metadataMatches =
                        first.isSingleton("primaryRepo")
                        && first.isSingleton("archiveRepo")
                        && first.isPrototype("ticket");

                verify(repeatedSame, "Same bean lookup differs");
                verify(aliasSame, "Alias is not same bean");
                verify(definitionsDistinct,
                        "Different definitions unexpectedly shared");
                verify(sameClass, "Repositories not same class");
                verify(consumersShare,
                        "Consumers did not share primary bean");
                verify(separateContexts,
                        "Contexts did not own separate objects");
                verify(prototypeDistinct,
                        "Prototype lookups returned same object");
                verify(manualOutside,
                        "Manual new must not be managed lookup");
                verify(metadataMatches,
                        "Unexpected Spring scope metadata");
                verify(!firstResource.isClosed(),
                        "First resource closed too early");
                verify(!secondResource.isClosed(),
                        "Second resource closed too early");

                System.out.println("sameLookup=" + repeatedSame);
                System.out.println("aliasSame=" + aliasSame);
                System.out.println("sameClass=" + sameClass);
                System.out.println("differentBeanDefinitions=" +
                        definitionsDistinct);
                System.out.println("consumersShare=" + consumersShare);
                System.out.println("differentContexts=" +
                        separateContexts);
                System.out.println("prototypeDifferent=" +
                        prototypeDistinct);
                System.out.println("manualNewDifferent=" +
                        manualOutside);
                System.out.println("scopeMetadataCorrect=" +
                        metadataMatches);
            }

            verify(firstResource.isClosed(),
                    "First context must close its resource");
            verify(!secondResource.isClosed(),
                    "Second context must remain active");

            System.out.println("firstResourceClosed=" +
                    firstResource.isClosed());
            System.out.println("secondResourceStillOpen=" +
                    !secondResource.isClosed());
        }

        verify(secondResource.isClosed(),
                "Second context must close its resource");
        System.out.println("secondResourceClosed=" +
                secondResource.isClosed());
    }
}
```

The code has a single top-level public class, with nested static domain classes to save files. `@Configuration(proxyBeanMethods=false)` is used because **every `@Bean` method receives its managed dependencies via parameters** rather than directly calling another factory method.

The two methods `catalogService`/`auditService` share the return type `CatalogService` yet are two separate singleton definitions, while both consumers retain **the same instance** of `NamedRepository` under the bean name `primaryRepo`.

### 14.3. Run command and expected stdout

Inside the `spring-singleton-boundaries` directory:

```bash
gradle run --quiet
```

If using the Gradle Wrapper:

```bash
./gradlew run --quiet
```

Windows PowerShell:

```powershell
.\gradlew.bat run --quiet
```

Lines produced by `System.out.println`:

```text
sameLookup=true
aliasSame=true
sameClass=true
differentBeanDefinitions=true
consumersShare=true
differentContexts=true
prototypeDifferent=true
manualNewDifferent=true
scopeMetadataCorrect=true
firstResourceClosed=true
secondResourceStillOpen=true
secondResourceClosed=true
```

Depending on Gradle/logging backend, the terminal may print additional lines beyond the application stdout. The program fails with `AssertionError` if a contract does not hold, rather than merely "printing values for the learner to guess".

### 14.4. Why is each result correct?

**`sameLookup=true`:** Calling `getBean("primaryRepo")` twice in the same container returns the managed singleton. Spring does not invoke `primaryRepo()` again on each lookup.

**`aliasSame=true`:** `repoAlias` is an alias of `primaryRepo`, so both names point to the same bean.

**`sameClass=true` and `differentBeanDefinitions=true`:** `primaryRepo` and `archiveRepo` are both `NamedRepository` yet are created by two different `@Bean` definitions. Each factory method instantiates a separate object with `new`.

**`consumersShare=true`:** both `catalogService` and `auditService` factory methods request `@Qualifier("primaryRepo") NamedRepository`, so Spring passes the same managed primary repository to both consumers.

**`differentContexts=true`:** two `AnnotationConfigApplicationContext` instances are created independently; each context calls its own factory method to create its primary repository. They do not use a shared static object.

**`prototypeDifferent=true`:** `Ticket` has `@Scope(PROTOTYPE)`, so two lookups in the same container create two objects.

**`manualNewDifferent=true`:** `new NamedRepository("manual")` is an independent object outside the `primaryRepo` registration. Spring does not equate a new raw object with a cached bean merely because the Java class matches.

**`scopeMetadataCorrect=true`:** the registry reports both repository beans as singleton and `ticket` as prototype. Metadata tests complement identity tests rather than replacing them.

**The three Resource lines:** context `first` closes before context `second`. The `ManagedResource` belonging to `first` receives `close()` while the resource belonging to `second` remains open. When `second` closes, its resource is closed then. This is lifecycle ownership per **container**, not per Java class.

### 14.5. Limitations of the demo

The example does not prove that every bean from two contexts always has different identity: a factory method returning a static shared object or child context delegation can cause two lookups to return the same object. The demo uses `new` inside each factory method and two independent containers to isolate the standard rule.

It also does not cover AOP proxies, `FactoryBean`, web session/request scopes, or mutating a singleton under concurrent load. Those topics have their own semantics requiring additional tests.

## 15. Debugging: when does a "singleton" appear to be created multiple times?

### 15.1. Multiple contexts exist without being noticed

A test suite, web app, or child-context setup can create multiple `ApplicationContext` instances. If constructor logs appear multiple times, check **how many containers exist** rather than jumping to the conclusion that Spring violated singleton scope.

### 15.2. Registering the same class under multiple bean names

Two `@Bean` methods or XML `<bean>` definitions using the same class can create two objects. Use `getBeanDefinitionNames()`/`getBeansOfType(...)` to inspect them.

### 15.3. Object created with `new` outside BeanFactory

Code such as:

```java
var rawService = new CatalogService(new Repository());
```

does not receive Spring's shared singleton even though the domain classes are the same. If Spring also has `@Bean CatalogService`, at least one raw instance and one managed instance will exist. Do not attribute scope semantics to every object of an annotated class.

### 15.4. Direct calls to a `@Bean` method in lite mode

With `proxyBeanMethods=false`, an inter-bean call `repository()` is a plain Java method invocation and can create an object outside the managed definition. Use parameters instead of direct method calls.

### 15.5. The bean actually has `@Scope("prototype")`

An overriding annotation, meta-annotation, XML definition, or custom scope can make a bean non-singleton. Check `isSingleton(name)`/`isPrototype(name)` in the exact context in use and understand proxy/factory semantics.

### 15.6. Proxy and target are not the same object

An AOP proxy can differ from the raw target object. Evaluating `proxy == target` can be false, yet the managed bean exposed via `getBean(name)` is still a singleton. Compare references at **the same layer**; do not mix raw objects and proxies.

### 15.7. FactoryBean returns a product with a different scope

`FactoryBean#isSingleton()` governs product caching separately; the factory bean itself has its own definition scope. Distinguish `&beanName` and `beanName` when investigating instance counts.

### 15.8. Test context gets rebuilt

`@DirtiesContext` or test configuration changes can cause Spring TestContext to close/recreate the context, legitimately causing singleton beans to be newly created. Changing profiles/mock beans/property sources can produce a different cache key.

### 15.9. Lazy singleton not yet created at startup

The singleton bean definition exists yet its constructor has not run because of `@Lazy`. The first `getBean` triggers creation; this is not a prototype. Check `isSingleton` and `containsSingleton` instead of just counting logs.

### 15.10. Bean created twice due to lifecycle/circular reference issues

In complex configurations, `BeanPostProcessor`/proxy/circular dependency failures or application-level retries can lead to multiple constructor logs even though only one final instance is published under the bean name. Do not rely on the number of constructor log lines as **standalone proof** of the singleton cache; inspect bean definitions, proxying, and the exception chain.

## 16. How to intentionally test scope and ownership

### 16.1. Identity test within the same context

```java
Object a = context.getBean("primaryRepo");
Object b = context.getBean("primaryRepo");
assert a == b;
```

Using Java assertions requires enabling `-ea` at runtime, or use JUnit `assertSame(a,b)` to avoid depending on a JVM flag. The section 14 demo uses a `verify(...)` helper that throws `AssertionError` directly.

### 16.2. Multiple definitions test

```java
Object a = context.getBean("primaryRepo");
Object b = context.getBean("archiveRepo");
assert a != b;
```

This is the expected result if two factory definitions create separate objects. If the factory methods intentionally return a shared static instance, the test must account for that different contract.

### 16.3. Context isolation test

```java
Object left = first.getBean("primaryRepo");
Object right = second.getBean("primaryRepo");
assert left != right;
```

This holds when `first` and `second` are **two containers owning separate definitions** and do not use a static shared instance/factory delegation. It does not apply blindly to a child context looking up a parent's bean.

### 16.4. Alias test

```java
Object primary = context.getBean("primaryRepo");
Object alias = context.getBean("repoAlias");
assert primary == alias;
```

If they are not equal, check whether the alias is properly registered and whether the lookups are against the same context.

### 16.5. Consumer reference test

```java
CatalogService a = context.getBean(
        "catalogService", CatalogService.class);
CatalogService b = context.getBean(
        "auditService", CatalogService.class);

assert a != b;
assert a.repository() == b.repository();
```

This is a neat point: **two different service singleton objects** still **share the same singleton repository**. Learners often confuse "injecting the same type" with "only one service instance across the entire context".

### 16.6. Lifecycle isolation test

Close one context while the other remains active; verify that the singleton resource owned by the closed context is cleaned up while the resource in the open context remains active. Do not use global static counters if they blur boundaries across contexts; use instance state as in the demo.

### 16.7. Concurrency test

For a singleton counter, run multiple threads calling `incrementAndGet` and assert the exact total when using an atomic/lock. This test verifies **thread safety of business state**, rather than directly testing singleton scope. Always keep the two assertions separate.

## 17. Common misconceptions

| Misconception | Reality |
| --- | --- |
| "Singleton = one instance per Java class" | A Spring singleton is per bean definition within one container |
| "A JVM has only one Spring singleton of class X" | A JVM can have multiple contexts and multiple definitions |
| "Two `@Bean` methods with the same return class must share an object" | Each bean definition is independent unless the factory returns a shared reference |
| "A bean alias creates a new singleton" | An alias is another name for the same bean definition |
| "`@Component` automatically guarantees no second definition exists" | Multiple registration sources can create different definitions |
| "Two services injecting `Repository` cause Spring to copy `Repository`" | The managed singleton dependency is shared within the same context |
| "Singleton = always created at JVM startup" | Scope differs from creation timing; `@Lazy` and dependency-driven creation exist |
| "Singleton = entire state is thread-safe" | The container ensures safe publication, while business state still requires synchronization |
| "`@Bean` method is always singleton even if called directly" | Direct Java calls in lite mode are not `BeanFactory` lookups |
| "Prototype = a new instance after every service method call" | Prototypes are created per lookup; singleton injection resolves only once |
| "A singleton resource is automatically shared by two contexts" | Normally each container has its own instance; factories returning statics are an exception |
| "`getBeanDefinitionCount()` equals the number of objects" | Definitions, aliases, proxies, `FactoryBean`s, and scopes create differences |
| "`getClass()` reveals every detail of the target bean" | AOP/scoped proxies have a runtime class different from the target |
| "Closing the context auto-cleans up every prototype" | Prototype cleanup is normally the responsibility of the consumer/owner |
| "Child and parent singleton caches are always isolated on every lookup" | A child can delegate lookup to a parent-owned singleton |
| "A singleton `FactoryBean` always returns a singleton product" | Factory scope and `FactoryBean#isSingleton()` are two separate layers |
| "A static singleton is definitely safe when closed by multiple contexts" | A shared resource can be destroyed multiple times |
| "Simply adding `@Primary` leaves only one bean" | `@Primary` selects a default candidate; it does not remove other beans |
| "Calling `new Repository()` yields a Spring bean because the class is annotated" | A raw object does not become a managed bean merely from a class annotation |
| "Multiple constructor log lines prove Spring created multiple final singleton instances" | You must inspect containers, proxies, failed creations, and identity |

## 18. Exercises with Answers

### Exercise 1 — One class, two definitions

In one context:

```java
@Bean("left") Store left() { return new Store("left"); }
@Bean("right") Store right() { return new Store("right"); }
```

Can both bean names have singleton scope? And do they share the same instance?

**Answer:** Yes, each definition is a singleton. With `new` factory methods as above, they create two separate instances.

### Exercise 2 — One definition, two lookups

What does calling `getBean("left")` twice in one context return?

**Answer:** The same managed singleton reference if bean `left` is a singleton.

### Exercise 3 — Two contexts

Two independent `AnnotationConfigApplicationContext` instances both register a `@Bean Store store(){return new Store();}`. Is the same instance guaranteed?

**Answer:** No. Each context normally creates/caches its own `Store`; returning a shared static instance is an exception caused by factory code.

### Exercise 4 — Aliases

Does `@Bean(name={"store","sharedStore"})` create two bean definitions?

**Answer:** No. `sharedStore` is an alias of `store`; when scoped as singleton, both lookups return the same reference.

### Exercise 5 — Two consumers

Service A and B both inject `@Qualifier("store") Store`. If `Store` is a singleton, how many `Store` objects do A and B hold?

**Answer:** One shared `Store` reference from that bean definition within the same context.

### Exercise 6 — Java `new`

Does `new Store()` in a unit test return the object from `context.getBean(Store.class)`?

**Answer:** No, unless you explicitly register/return that exact object; normally `new` is independent of the Spring registry.

### Exercise 7 — Lazy singleton

`@Bean @Lazy Store store()`, after refresh `containsSingleton("store")` can be false. Does that prove prototype scope?

**Answer:** No. The bean definition is still singleton; it simply has not been instantiated yet.

### Exercise 8 — Primary

There are two `DataSource` beans, one `@Primary`. Does the other bean stop being a singleton?

**Answer:** No. Both definitions can be singletons; `@Primary` only helps select a single dependency.

### Exercise 9 — Prototype into singleton

A singleton `ReportService` injects a prototype `Ticket` once via constructor. Does every `report()` call get a new `Ticket`?

**Answer:** No; the singleton holds the prototype object that was injected. If a new one is needed per operation, use a provider/factory lookup.

### Exercise 10 — Direct prototype

Do two `context.getBean("ticket")` calls with prototype scope and a factory always calling `new Ticket()` return the same object?

**Answer:** No, each lookup receives a new instance.

### Exercise 11 — Safe publication

A singleton has immutable configuration set before initialization completes. Do other threads looking it up from the container have proper visibility?

**Answer:** The container guarantees safe publication for initialized singletons. However, updates **after startup** still require concurrency controls under the Java Memory Model.

### Exercise 12 — Mutable counter

A singleton controller has an `int hits` field and a `hits++` method called concurrently. Does Spring automatically guarantee the right result?

**Answer:** No. You need `AtomicInteger`, synchronization, or to avoid shared mutable state.

### Exercise 13 — Scoped proxy

A singleton service holds the same proxy reference to a request bean. Do all requests use one target object?

**Answer:** No. The proxy reference can be a singleton, while the request target changes per request scope.

### Exercise 14 — Child/parent

A child has no local `repo` bean and looks up the parent bean. Can it return the same reference as the parent?

**Answer:** Yes; the child delegates the lookup to the parent-owned singleton without creating a local copy.

### Exercise 15 — Child overriding a name

The parent has a `repo` singleton, and the child registers a new `repo` definition. Must a lookup from the child return the parent's object?

**Answer:** No; the local name can shadow the parent. Check the actual parent-child lookup/overriding policies.

### Exercise 16 — FactoryBean

A `FactoryBean` definition is singleton, yet `FactoryBean#isSingleton()` for the product returns false. Is a product lookup guaranteed to return a single unique instance?

**Answer:** No. Factory object scope and product caching are two separate semantics.

### Exercise 17 — Calling a `@Bean` method directly

In `@Configuration(proxyBeanMethods=false)`, the `service()` method manually calls `repository()`. Is it guaranteed to receive the repository from the bean cache?

**Answer:** No. The call is plain Java; use factory method parameter injection.

### Exercise 18 — Destroy callbacks

Two contexts each have their own `ManagedResource`. Does closing context A automatically close the resource belonging to B?

**Answer:** No, under normal ownership; only the resource managed by A is cleaned up by A. If both factories intentionally return a shared static object, watch out for double-close lifecycle issues.

### Exercise 19 — Test context caching

Two test methods use the same Spring TestContext configuration. Are they guaranteed to create two different `ApplicationContext` instances?

**Answer:** No. Spring TestContext has a caching/reuse policy; you must verify the actual context identity.

### Exercise 20 — Bean names and types

`@Bean("alpha") Client alpha()` and `@Bean("beta") Client beta()`, both singletons. Is `getBean(Client.class)` guaranteed to pick one?

**Answer:** No. When there are multiple candidates with no single winner, type lookup/injection can be ambiguous; use a qualifier, `@Primary`, or named lookup.

## 19. Practice Checklist

- Have you clearly identified which **bean name/definition** is being discussed?
- Are you confusing Java class identity with Spring bean registration identity?
- How many `ApplicationContext`/`BeanFactory` instances are running?
- If using parent/child contexts, which container owns the bean?
- Are there aliases or multiple definitions of the same class?
- Do `@Bean` factory methods return a static shared object themselves?
- Is the scope singleton, prototype, or a web/custom scope? Is there a proxy?
- Does injection into a shared bean use the right `@Qualifier`/named reference when multiple candidates exist?
- Does `@Configuration(proxyBeanMethods=false)` contain risky direct inter-bean calls?
- Is any code manually calling `new` for a dependency that should come from the container?
- Has `@Lazy` left a bean uninstantiated at refresh? Is an eager consumer triggering it?
- Have you distinguished `containsSingleton`, `isSingleton`, and `containsBean`?
- Have you checked reference identity with `==`/`assertSame` instead of hash codes/log text?
- Does the singleton hold mutable request/user data causing races/leaks?
- Does mutable state after init use appropriate locks, atomics, or concurrent structures?
- Do managed singleton resources have destroy callbacks and get closed by the right context?
- Do prototype resources have their own cleanup owner?
- Are tests using context caching that breaks isolation assumptions?
- Are `FactoryBean` products and factory instances being confused when calling `&name`?
- If "one instance across the entire JVM" is needed, is that truly a requirement or just misuse of global state?

## 20. Conclusion

**A Spring singleton is a container scope policy, not a Java class Singleton pattern.** A singleton bean definition in a Spring container is managed by the container as a single shared instance; multiple lookups and consumers for the same bean receive the same managed reference. Two beans of the same class with different definitions can still hold separate instances. Two independent containers typically also have separate caches/instances. An alias provides multiple names for the same bean, not an extra definition.

Understanding the exact boundaries helps you explain why an application has two `Repository` objects even though both are singletons, why an object is recreated when an integration test builds a new context, and why a singleton bean's constructor can run during context refresh or later with `@Lazy`.

Finally, **singleton does not mean thread-safe mutable state**, nor does it mean global resource ownership. Spring guarantees container-side safe publication, while business code must still design concurrency and cleanup properly. Verify by checking bean names, context identity, scopes, object references with `==`, and lifecycle tests.

### Official Spring Framework Documentation

- [Spring Framework 6.2 — Bean Scopes / Singleton Scope](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html).
- [Spring Framework 6.2 — Using the `@Bean` Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html).
- [Spring Framework 6.2 — Basic Concepts: `@Bean` and `@Configuration`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/basic-concepts.html).
- [Spring Framework 6.2 — Using `@Configuration` and inter-bean method calls](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/configuration-annotation.html).
- [Spring Framework 6.2 — Bean Factory API](https://docs.spring.io/spring-framework/reference/6.2/core/beans/beanfactory.html).
- [Spring Framework 6.2 — Bean Lifecycle and Thread Safety/Visibility](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html).
- [Spring Framework 6.2 — Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-lazy-init.html).
- [Spring Framework 6.2 — Singleton beans with prototype dependencies](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html#beans-factory-scopes-prototype).
