# Distinguishing FactoryBean from BeanFactory in the Spring Core Container

## 1. Why are these two names easily confused?

`BeanFactory` and `FactoryBean` have very similar names, but they belong to **two different levels** of Spring IoC:

- **`BeanFactory`** is the foundational interface of the **container**. It manages looking up beans by name/type, creating objects when needed, and applying scopes, dependencies, and lifecycle callbacks through a concrete implementation.
- **`FactoryBean<T>`** is an interface implemented by **a special bean**. That bean acts as a factory that produces **a product `T`**. When the application calls `getBean("tenFactory")`, Spring normally returns **the product created by `FactoryBean.getObject()`**, rather than the factory object itself.

A way to remember:

```text
                  +---------------------------+
                  | BeanFactory (container)   |
                  | - bean definitions        |
                  | - dependency wiring       |
                  | - scopes/lifecycle        |
                  +---------------------------+
                              |
                   getBean("widget")
                              |
                              v
                     [WidgetFactory]
                    implements FactoryBean
                              |
                         getObject()
                              |
                              v
                         Widget
                        (product)

getBean("&widget") ------------------> WidgetFactory
                                         (factory itself)
```

In the diagram, the container **holds a bean definition for `WidgetFactory`**; under the `FactoryBean` contract, the normal name `widget` **exposes the product**. If you need to retrieve the object that produces the product to configure or inspect it directly, Spring supports the `&` prefix in the bean name.

**The most important difference:** `BeanFactory` **manages many beans**; a `FactoryBean` **is a special bean that creates or supplies one kind of product** inside the BeanFactory.

## 2. Direct comparison

| Criterion | `BeanFactory` | `FactoryBean<T>` |
| --- | --- | --- |
| API package | `org.springframework.beans.factory.BeanFactory` | `org.springframework.beans.factory.FactoryBean` |
| Role | IoC container contract | Extension point to customize how a bean/product is created |
| Who typically implements it? | The Spring container, e.g., `DefaultListableBeanFactory` | Developers/libraries, e.g., factories for proxies, clients, products |
| Managed objects | Bean definitions and all beans managed by the container | The product of a specific factory |
| Commonly used API | `getBean(...)`, `containsBean(...)`, `isSingleton(...)`, `getType(...)` | `getObject()`, `getObjectType()`, `isSingleton()` |
| Access | Inject/receive `ApplicationContext`, `BeanFactory`, or use a sub-interface | Register a `FactoryBean` as a bean and look it up by bean name |
| `getBean("x")` | The container resolves the object named `x` | If `x` is a FactoryBean, normally returns its product |
| `getBean("&x")` | The container interprets `&` as a factory dereference | Returns the FactoryBean instance itself behind `x` |
| Scope | The container enforces singleton/prototype/custom scopes | The factory's scope and the product's singleton status are **two separate decisions** |
| Lifecycle | The container controls the lifecycle of the beans it owns | The FactoryBean itself is a managed bean; the product requires separate lifecycle attention |
| Commonality in business code | Usable, though constructor injection is usually preferred | Useful for complex object creation mechanisms, especially infrastructure code |

`BeanFactory` is an **interface**, not a "factory bean" instance by naming convention. `FactoryBean` is also an **interface**, not a `BeanFactory` implementation.

## 3. BeanFactory: the core contract of the IoC container

Some representative methods:

```java
Object getBean(String name);
<T> T getBean(String name, Class<T> requiredType);
<T> T getBean(Class<T> requiredType);
boolean containsBean(String name);
boolean isSingleton(String name);
boolean isPrototype(String name);
Class<?> getType(String name);
```

This is an **illustrative signature snippet**, not standalone compilable code. Other overloads and annotations have been omitted.

The container's general responsibilities:

1. Hold bean definitions and know whether to create a bean from a constructor or a factory method.
2. Resolve the dependency graph; create dependent beans before passing them into the bean that needs the dependency.
3. Apply scopes (singleton, prototype, and custom/web scopes when registered).
4. Execute `BeanPostProcessor`s, init callbacks, and destruction callbacks if the lifecycle belongs to the container.
5. Provide APIs to look up objects and type/scope information.

`ApplicationContext` extends the BeanFactory system with environment, resource loading, events, internationalization, and many convenience lifecycle features. In Spring applications, `AnnotationConfigApplicationContext` is a type of `ApplicationContext` that supports `BeanFactory` APIs.

Usage example:

```java
try (AnnotationConfigApplicationContext context =
             new AnnotationConfigApplicationContext(MyConfig.class)) {
    BeanFactory factory = context;
    PaymentService service = factory.getBean(PaymentService.class);
    service.process();
}
```

This is an **example snippet** that requires `MyConfig` and `PaymentService` to actually exist with appropriate imports. It shows that a variable of type `BeanFactory` is an interface for accessing the container; it does not by itself designate any bean as a `FactoryBean`.

### BeanFactory differs from DefaultListableBeanFactory

`BeanFactory` defines the operations clients need; `DefaultListableBeanFactory` is the common implementation, containing the registry, bean definition metadata, and actual bean creation mechanisms. `ConfigurableListableBeanFactory`, `ConfigurableBeanFactory`, and `ListableBeanFactory` are other interfaces that provide additional configuration/listing capabilities.

You should not write business code that depends directly on `DefaultListableBeanFactory` to mutate the registry when constructor injection is sufficient. Separating the **container API** from the **container implementation** makes unit tests and module design simpler.

## 4. FactoryBean<T>: a bean that exposes its own product

The full interface has three core methods:

```java
public interface FactoryBean<T> {
    T getObject() throws Exception;
    Class<?> getObjectType();
    default boolean isSingleton() {
        return true;
    }
}
```

This is an **abbreviated illustrative signature** per Spring Framework 6.2. The actual API has annotations, Javadoc, and may include additional metadata.

### 4.1. getObject()

`getObject()` creates, returns, or retrieves from cache the product of the FactoryBean. Depending on `isSingleton()`, Spring may cache the product returned by the factory. Do not assume that every call to `BeanFactory.getBean("x")` directly invokes `FactoryBean.getObject()`.

If `isSingleton()==true` and the bean factory supports caching, after the product is created, subsequent lookups under the same name normally use the cached product.

If `isSingleton()==false`, Spring does not apply that singleton product cache; each lookup normally requests `getObject()`. **The FactoryBean must guarantee an independent creation contract itself** if true prototype behavior is desired.

### 4.2. getObjectType()

`getObjectType()` reports the type of the product, not the type of the factory itself. Spring needs this information for type matching/autowiring without unnecessarily creating the product.

```java
@Override
public Class<?> getObjectType() {
    return Widget.class;
}
```

This is an illustrative method snippet, assuming `Widget` is the product type. The method should be fast, avoid side effects, and **not call `getObject()` just to guess the product type**. According to the Javadoc, the method may be called before the FactoryBean has completed initialization; do not rely on state that is only set late in init callbacks.

If the type is unknown, `getObjectType()` is allowed to return `null`, but Spring cannot use that type to reliably resolve certain autowiring/type searches. This is a last resort and should not be the default when the product type is already known.

### 4.3. isSingleton()

`FactoryBean.isSingleton()` describes whether the **product** is a singleton; the default is `true`.

```java
@Override
public boolean isSingleton() {
    return false; // The product is not a singleton.
}
```

Do not misread `isSingleton()` as "the FactoryBean object is a singleton": the factory object is registered with its own scope (usually singleton by default). The two layers of scope must be considered independently.

When returning `true`, the FactoryBean must provide a product with a stable identity: calls to `getObject()` under the contract should not silently create different products. The container may cache the product, but the implementation must still remain consistent if the method is used directly.

## 5. Bean naming rule: & to retrieve the factory

Suppose there is a bean named `widget`, defined by a class implementing `FactoryBean<Widget>`:

```java
Object product = context.getBean("widget");
Object factory = context.getBean("&widget");
```

Explanation:

- `"widget"`: the logical name under which Spring exposes the **product**.
- `"&widget"`: the `BeanFactory.FACTORY_BEAN_PREFIX` prefix helps **dereference the factory**, retrieving the bean itself that implements `FactoryBean`.
- `"widget"` is still the bean name registered in the registry. You do **not** register a separate definition named `"&widget"`.
- `&` is a syntactic mechanism of Spring BeanFactory, **not** a Java address-of operator.
- Calling `getBean("&ordinaryBean")` when that bean does not implement `FactoryBean` causes an error such as `BeanIsNotAFactoryException`.

A type-safe approach when needed:

```java
Widget widget = context.getBean("widget", Widget.class);
WidgetFactory factory = context.getBean("&widget", WidgetFactory.class);
```

This snippet requires the corresponding bean names/types to already be registered. The `WidgetFactory` type only exists in the example in section 7.

### Type-based lookup is also affected

`getBean(Widget.class)` can resolve the FactoryBean's product through `getObjectType()` and metadata. Conversely, if you want the factory itself, you should explicitly specify the `&` prefix or design wiring for the factory explicitly. Do not assume Spring will treat the FactoryBean itself as an ordinary bean for **every type of lookup** by its Java class.

For `getBeansOfType` listings or an injection point, the result also depends on type inference, candidate uniqueness, and how Spring handles FactoryBean instances. Using `&name` is the clearest way to express that you need the factory itself.

## 6. Two layers of scope to distinguish

This is the most common mistake when learning FactoryBean. There are **two separate questions**:

**Question A: how many times is the FactoryBean itself created?**

It is a container-managed bean. If the `@Bean("widget")` definition has no `@Scope`, Spring defaults to **singleton scope for the factory**. If the factory is declared prototype, each time BeanFactory needs to create a factory instance it may produce a new factory.

**Question B: is the product supplied by the FactoryBean cached?**

`FactoryBean.isSingleton()` answers this question. With a singleton factory:

| Factory scope | Product's `isSingleton()` | Commonly observed behavior |
| --- | --- | --- |
| singleton | `true` | Same factory, same product across normal lookups |
| singleton | `false` | Same factory, product does not use singleton cache; may be re-created on each lookup |
| prototype | `true` | Each access to the definition may create a new factory; do not assume a container-wide singleton product |
| prototype | `false` | A new factory can create a new product per lookup |

The table describes tendencies to distinguish the two dimensions; do not use it as a substitute for checking the bean definition, `FactoryBean` contract, and the implementation's creation/caching strategy.

If the returned product belongs to a custom scope such as request/session, `isSingleton()==false` **does not by itself prove that every call yields an independent instance**. `SmartFactoryBean.isPrototype()` is designed to express more clearly the returning of independent objects. Therefore, **"non-singleton" does not always mean "prototype"** in all special factory scenarios.

## 7. Runnable Java 17+ example: two factories, two product strategies

Minimal project with Spring Framework 6.2.x, without Spring Boot:

```text
factory-vs-beanfactory/
├── settings.gradle
├── build.gradle
└── src/main/java/FactoryDifferenceDemo.java
```

### settings.gradle

```groovy
rootProject.name = 'factory-vs-beanfactory'
```

### build.gradle

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'FactoryDifferenceDemo'
}
```

### src/main/java/FactoryDifferenceDemo.java

```java
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.BeanFactory;
import org.springframework.beans.factory.FactoryBean;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class FactoryDifferenceDemo {

    public record Widget(int number) {
    }

    public static class WidgetFactory implements FactoryBean<Widget> {
        private final boolean productSingleton;
        private final AtomicInteger sequence = new AtomicInteger();
        private Widget sharedProduct;

        public WidgetFactory(boolean productSingleton) {
            this.productSingleton = productSingleton;
        }

        @Override
        public synchronized Widget getObject() {
            if (productSingleton) {
                if (sharedProduct == null) {
                    sharedProduct = new Widget(sequence.incrementAndGet());
                }
                return sharedProduct;
            }
            return new Widget(sequence.incrementAndGet());
        }

        @Override
        public Class<?> getObjectType() {
            return Widget.class;
        }

        @Override
        public boolean isSingleton() {
            return productSingleton;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        // The factory bean is a singleton under the default scope.
        // The product is also provided under the singleton contract.
        @Bean("sharedWidget")
        public WidgetFactory sharedWidget() {
            return new WidgetFactory(true);
        }

        // The factory bean is still a singleton,
        // but a new product is created on lookup.
        @Bean("freshWidget")
        public WidgetFactory freshWidget() {
            return new WidgetFactory(false);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            // ApplicationContext also provides the BeanFactory API.
            BeanFactory beanFactory = context;

            Widget shared1 =
                    beanFactory.getBean("sharedWidget", Widget.class);
            Widget shared2 =
                    beanFactory.getBean("sharedWidget", Widget.class);

            Widget fresh1 =
                    beanFactory.getBean("freshWidget", Widget.class);
            Widget fresh2 =
                    beanFactory.getBean("freshWidget", Widget.class);

            WidgetFactory factory1 =
                    beanFactory.getBean("&freshWidget", WidgetFactory.class);
            WidgetFactory factory2 =
                    beanFactory.getBean("&freshWidget", WidgetFactory.class);

            System.out.println("sharedSame=" + (shared1 == shared2));
            System.out.println("freshDifferent=" + (fresh1 != fresh2));
            System.out.println("sharedNumbers="
                    + shared1.number() + "," + shared2.number());
            System.out.println("freshNumbers="
                    + fresh1.number() + "," + fresh2.number());
            System.out.println("factorySame=" + (factory1 == factory2));
            System.out.println("factoryClass="
                    + factory1.getClass().getSimpleName());
            System.out.println("productClass="
                    + fresh1.getClass().getSimpleName());
            System.out.println("factorySingletonProduct="
                    + factory1.isSingleton());
            System.out.println("contextIsBeanFactory="
                    + (context instanceof BeanFactory));
        }
    }
}
```

Run with JDK 17+ and Gradle 8+:

```bash
gradle run --quiet
# Or ./gradlew run --quiet if the project already has a Gradle Wrapper.
```

**Lines printed by the program via `System.out`:**

```text
sharedSame=true
freshDifferent=true
sharedNumbers=1,1
freshNumbers=1,2
factorySame=true
factoryClass=WidgetFactory
productClass=Widget
factorySingletonProduct=false
contextIsBeanFactory=true
```

There may be framework logs depending on the classpath/configuration; they do not change the listed `System.out` lines.

### Analysis of each result

1. Two calls to `getBean("sharedWidget")` return **the same `Widget`**. The factory has `isSingleton()==true`, Spring can cache the singleton product, and the factory itself also preserves the product's identity in `sharedProduct`.
2. Two calls to `getBean("freshWidget")` return **two different `Widget`s**, because the FactoryBean reports `isSingleton()==false` and `getObject()` creates a new product.
3. Each factory's sequence is independent. Therefore the singleton product has the number `1` twice, while the non-singleton has `1` then `2`.
4. Two calls to `getBean("&freshWidget")` return **the same factory instance**: the `freshWidget` definition has the default singleton scope.
5. The factory type is `WidgetFactory`; the product type is `Widget`. They are two distinct Java objects.
6. `factorySingletonProduct=false` describes the factory's **product cache policy**, even though `WidgetFactory` itself is a singleton.
7. `contextIsBeanFactory=true` because `ApplicationContext` extends BeanFactory capabilities. `BeanFactory` is not a `WidgetFactory`.

**Example note:** `WidgetFactory.getObject()` is synchronized with `synchronized` to illustrate safe shared-product initialization under concurrent calls. The code still executes independent logic inside each factory without a static cache; real applications need to choose synchronization/caching suitable for their load and lifecycle.

## 8. @Bean factory method differs from FactoryBean

In Java configuration, the `@Bean` syntax on a method is usually enough to create a bean:

```java
@Configuration(proxyBeanMethods = false)
class RegularConfig {
    @Bean
    Widget widget() {
        return new Widget(42);
    }
}
```

This is an illustrative snippet. `widget()` is a **factory method** in the ordinary sense: Spring calls the method to create a bean of type `Widget`. It **does not automatically turn `RegularConfig` into a `FactoryBean<Widget>` implementation**.

Compare three cases:

| Registration method | Object the container receives from the definition | `getBean("widget")` |
| --- | --- | --- |
| `@Bean Widget widget()` | Ordinary `Widget` bean | Returns `Widget` |
| `@Bean WidgetFactory widget()` with `WidgetFactory implements FactoryBean<Widget>` | Special `WidgetFactory` bean | Returns `Widget` as the product; `&widget` returns the factory |
| XML definition class implementing `FactoryBean` | Bean implementing FactoryBean | Returns the product; `&widget` returns the factory |

A `@Bean` method can return a `FactoryBean`, in which case Spring applies dereference/product semantics. What makes a `FactoryBean` is not a method name containing the word "factory", but **an instance that actually implements `org.springframework.beans.factory.FactoryBean`**.

### When to use FactoryBean instead of a @Bean method?

Choose a `@Bean` factory method if object creation is easy to express:

```java
@Bean
HttpClient httpClient() {
    return HttpClient.newHttpClient();
}
```

Illustrative snippet assuming `java.net.http.HttpClient` on Java 17+. A regular method is sufficient.

Consider `FactoryBean` when you need to integrate a complex object creation abstraction into **container type matching and lookup semantics**, such as a proxy, a dynamic client, an object built by an external provider, or framework infrastructure that wants to manage the factory separately from the product. In simple business code, a `@Bean` method or a plain Java factory service is usually clearer.

## 9. FactoryBean differs from factory method and ObjectFactory<T>

Three concepts all contain the word "factory":

**`@Bean` factory method:** Spring invokes the configuration method to create the bean. The result can be an ordinary bean or a `FactoryBean`.

**`FactoryBean<T>`:** a special contract understood by the container; has `getObject()`, `getObjectType()`, and `isSingleton()`. The normal bean name exposes the product, `&name` exposes the factory.

**`ObjectFactory<T>`:** a very small interface with `T getObject()`, often used to request an object on demand, e.g., injected into a singleton to obtain a prototype; an object implementing `ObjectFactory` does not by default have the `&` prefix mechanism.

Container injection pattern:

```java
@Service
class ReportRunner {
    private final ObjectProvider<ReportTask> tasks;

    ReportRunner(ObjectProvider<ReportTask> tasks) {
        this.tasks = tasks;
    }

    void run() {
        ReportTask task = tasks.getObject();
        task.execute();
    }
}
```

This is an **illustrative snippet**, requiring the corresponding imports and definitions for `ReportTask`, `@Service`, and `ObjectProvider`. `ObjectProvider` extends flexible lookup capabilities; if `ReportTask` has prototype scope, each `getObject()` can create a new instance.

Do not confuse `ObjectProvider<T>` (client-side lookup supporting injection) with `FactoryBean<T>` (container-level extension changing how a bean name exposes a product).

## 10. Lifecycle of FactoryBean and product

This is a limitation easily overlooked when building a `FactoryBean` that supplies a socket, connection pool, HTTP client, or heavy resource.

### 10.1. The FactoryBean object has a normal lifecycle

If the factory is a singleton managed by the context, it itself is created and initialized according to the bean lifecycle: dependency injection, init callbacks, BeanPostProcessors, and destruction callbacks when the context closes. You can use `DisposableBean` or a custom destroy method on the **factory**.

### 10.2. The product does not automatically get a full destruction lifecycle

According to the `FactoryBean` Javadoc, the container is responsible for managing the lifecycle of the **FactoryBean instance**; the product from `getObject()` **does not automatically have the same destruction lifecycle** simply because it is exposed via `getBean("name")`. In particular, do not expect Spring to automatically call `AutoCloseable.close()` on the product when the context closes.

Example of a factory managing a singleton product that needs closing:

```java
import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.FactoryBean;

final class ClientFactory
        implements FactoryBean<ManagedClient>, DisposableBean {

    private ManagedClient client;

    @Override
    public synchronized ManagedClient getObject() {
        if (client == null) {
            client = new ManagedClient();
        }
        return client;
    }

    @Override
    public Class<?> getObjectType() {
        return ManagedClient.class;
    }

    @Override
    public boolean isSingleton() {
        return true;
    }

    @Override
    public synchronized void destroy() throws Exception {
        if (client != null) {
            client.close();
        }
    }
}
```

This is an **illustrative class snippet**, requiring `ManagedClient implements AutoCloseable` with an appropriate constructor, and is not a complete standalone Java file. The factory is responsible for closing the product when the factory is destroyed. Cleanup should be written idempotently, taking into account thread safety, exceptions, and ownership if the product is shared.

With `isSingleton()==false`, callers may receive many different products; if each product holds a resource that needs closing, you must design one of the explicit strategies: the caller closes it after each task, the factory tracks them for controlled closing, or create a scoped resource with lifecycle support. You cannot just write `FactoryBean.destroy()` and assume every product ever created has been closed.

### Product and BeanPostProcessor

Spring may apply **some post-processing** to the product returned from a FactoryBean (notably post-initialization post-processing), but that **is not equivalent** to the product being created as an ordinary bean definition with full init and destroy callbacks. Do not rely on `@PostConstruct` on the product necessarily being called automatically just because the product class has the annotation. If the product needs explicit initialization, perform it in the factory or design an appropriate normal bean definition.

## 11. getObjectType() and type-based autowiring

A container may have to answer "is there a bean of type `PaymentGateway`?" **before creating the product**. Therefore, having the FactoryBean declare the right type is a prerequisite for stable wiring.

Good implementation:

```java
@Override
public Class<?> getObjectType() {
    return PaymentGateway.class;
}
```

This is an illustrative snippet. The factory returns an object compatible with `PaymentGateway`. Benefits:

- `getBeanNamesForType(PaymentGateway.class)` has a basis to find candidates.
- Constructor injection `PaymentGateway gateway` can be resolved when there is only one matching bean.
- IDEs/tooling and type checks have reliable metadata.

Risky implementation:

```java
@Override
public Class<?> getObjectType() {
    return getObject().getClass(); // Side effect: creates the product!
}
```

This is an anti-pattern: type introspection can execute `getObject()` prematurely, creating resources or starting connections while the container is still building metadata or during scanning. This can drag in circular dependencies and out-of-order initialization.

If the runtime type is truly dynamic, publish a stable interface/supertype that every product satisfies; return `null` only when the contract truly cannot determine the type.

`FactoryBean.OBJECT_TYPE_ATTRIBUTE` also allows declaring the product type on bean definition metadata in some cases, so the container can look up the type without instantiating the factory. This is an advanced detail for infrastructure, not a requirement for most custom FactoryBeans.

## 12. What if getObject() throws an exception or returns null?

`FactoryBean.getObject()` declares `throws Exception`. When it fails, the `BeanFactory.getBean("name")` call is normally translated by Spring into a bean-creation-related exception carrying the cause of the factory failure.

Several scenarios:

- **Misconfiguration:** the constructor or `getObject()` throws an exception when the product cannot be created.
- **Circular reference / factory not ready:** the implementation may throw `FactoryBeanNotInitializedException` to signal that the factory cannot create the object yet.
- **Returning `null`:** the contract allows returning `null` in certain cases; Spring has internal semantics to represent a null bean. However, consumers requiring non-null will fail to operate properly. For essential products, return a clear type/object and throw a meaningful exception if creation fails.
- **Thread safety:** multiple concurrent lookups may hit the factory logic. For a shared product, ensure synchronization; for prototypes, avoid holding unsafe mutable shared state.
- **Caching and retry:** do not put a broken product into a shared cache and let every subsequent lookup receive an invalid object.

When the product is a remote client that may fail to connect, do not create the connection in `getObjectType()`. If initialization can fail after opening resources, clean up in `getObject()` with `try/finally` or a clear helper to avoid leaks before returning.

## 13. SmartFactoryBean: extending singleton and eager-init metadata

Spring provides the `SmartFactoryBean<T> extends FactoryBean<T>` interface, supplying additional information to the container:

- `isPrototype()`: indicates whether the product is truly **an independent instance** each time it is created.
- `isEagerInit()`: hints whether the factory and singleton product need to be initialized eagerly during the pre-instantiation pass.

In particular:

```text
FactoryBean.isSingleton() == false
        does not always imply
SmartFactoryBean.isPrototype() == true
```

Because "not singleton" can mean an object bound to another scope, still reused within a specific lifetime. `SmartFactoryBean` is mainly for infrastructure/collaborating frameworks; application custom factories usually find `FactoryBean` sufficient.

An ordinary `FactoryBean` does not necessarily create the **product** during the startup eager singleton pass, even when the singleton **factory** is instantiated. The product is normally created on demand; `SmartFactoryBean.isEagerInit()` can change that.

## 14. Side by side with BeanFactoryPostProcessor and BeanPostProcessor

There is another group of names that are also easy to confuse:

| Component | Operates on | Timing |
| --- | --- | --- |
| `BeanFactory` | Container API for the bean graph | Throughout the lifecycle |
| `FactoryBean<T>` | Creating/exposing the product of a special bean factory | When the container needs the product, per cache/scope |
| `BeanFactoryPostProcessor` | BeanFactory and bean definition metadata | Before the normal singleton creation pass |
| `BeanDefinitionRegistryPostProcessor` | Bean definition registry, can add definitions | Before ordinary BFPPs |
| `BeanPostProcessor` | Bean instances | During the initialization of each bean |

A `FactoryBean` can also implement lifecycle interfaces if needed. But that **does not turn it into a `BeanFactoryPostProcessor`**. Having "Factory" in the name does not mean the API sits at the same point in the lifecycle.

For example, using a `BeanFactoryPostProcessor` to change scope metadata before beans are created is a completely different extension point from a custom `FactoryBean` used to create a client.

## 15. Dependency injection: getting the factory or getting the product?

Suppose you have:

```java
@Bean("gateway")
GatewayFactory gatewayFactory() {
    return new GatewayFactory();
}
```

This is an illustrative snippet, assuming `GatewayFactory implements FactoryBean<Gateway>`.

A consumer that wants the **product** normally injects the product interface:

```java
@Service
class PaymentService {
    private final Gateway gateway;

    PaymentService(Gateway gateway) {
        this.gateway = gateway;
    }
}
```

If type matching uniquely identifies the product, Spring resolves the dependency for `Gateway`. Business consumers do not need to know how the factory is implemented.

A consumer that wants the **factory**, only in infrastructure code, can access it via `&gateway`:

```java
GatewayFactory factory =
        context.getBean("&gateway", GatewayFactory.class);
```

Or the architecture can expose a separate bean facade/management interface so consumers are not forced to know the Spring prefix.

**Avoid injecting `BeanFactory` just to retrieve a fixed dependency.** For example:

```java
@Service
class FragilePaymentService {
    @Autowired
    BeanFactory container;

    void pay() {
        Gateway gateway = container.getBean("gateway", Gateway.class);
    }
}
```

The snippet above is not a complete program. It creates coupling to a string bean name. Constructor injection with `Gateway` is usually simpler, type-safe, and easier to test. For needing a prototype multiple times, consider `ObjectProvider<Gateway>`.

## 16. Testing FactoryBean and BeanFactory

### Testing the factory as a Java class

You can test `WidgetFactory` directly in the example from section 7:

```java
WidgetFactory factory = new WidgetFactory(false);
Widget one = factory.getObject();
Widget two = factory.getObject();

assert one != two;
assert factory.getObjectType() == Widget.class;
assert !factory.isSingleton();
```

This is an illustrative snippet, assuming nested classes are imported or fully qualified via `FactoryDifferenceDemo`; use `-ea` if running Java `assert`. This unit test verifies **the logic of the FactoryBean**, but **does not yet** verify container dereferencing and product caching.

### Testing through the Spring container

In an integration test, you should check:

```java
Object product = context.getBean("sharedWidget");
Object underlyingFactory = context.getBean("&sharedWidget");

assert product instanceof Widget;
assert underlyingFactory instanceof WidgetFactory;
assert context.getBean("sharedWidget") == product;
```

This is an illustrative snippet (with the `context` variable from the main example). It proves Spring understands the FactoryBean contract. Test lifecycle separately if the factory creates a resource with `close()`.

### Minimum scenarios to verify

1. `getBean("x")` returns the right product type.
2. `getBean("&x")` returns the factory, not the product.
3. `FactoryBean.getObjectType()` reports the right type without instantiating the product just to determine the type.
4. `isSingleton=true` and `getObject()` actually provide the same product identity.
5. `isSingleton=false` and the implementation actually provides a new product if prototype behavior is required.
6. Whether a singleton or prototype factory is created according to the configured scope.
7. Factory cleanup is managed by Spring, and product cleanup is managed by the factory/caller if needed.
8. Errors from `getObject()` are reported properly instead of returning a broken product.
9. If multiple product candidates have the same type, constructor injection must have a clear qualifier/name.

In JUnit 5, prefer `assertSame`/`assertNotSame` when comparing identity. `equals` only checks value, not whether two objects share the same reference.

## 17. Common errors and how to fix them

| Error/symptom | Cause | How to handle |
| --- | --- | --- |
| `getBean("factoryName")` returns the client instead of the factory class | FactoryBean is dereferenced to its product by Spring by default | Call `getBean("&factoryName")` to get the factory |
| `getBean("&regularBean")` throws `BeanIsNotAFactoryException` | The target bean does not implement `FactoryBean` | Remove `&` or use the proper factory bean definition |
| Product retrieved multiple times still has the same reference | `isSingleton()` defaults to `true`, so the container caches the product | Override `isSingleton()` to return `false` when the product is truly non-singleton |
| Product changes even though the factory returns `true` | The factory violates the singleton product contract | Keep a shared instance and ensure thread-safe initialization |
| Two `&name` calls return the same factory but different products | Factory scope is singleton, `isSingleton=false` | This is completely valid behavior, not a bug |
| Injecting the product by type fails to find the bean | `getObjectType()` returns `null` or the wrong type | Declare the proper type and avoid initializing the product in this method |
| Constructor/factory unexpectedly runs when inspecting type | `getObjectType()` calls `getObject()` or type inspection forces factory init | Remove the side effect; design metadata to be available upfront |
| Product's `AutoCloseable.close()` does not run on context close | The product does not automatically receive a full destruction lifecycle | Have the factory clean up/delegate or let the caller manage the resource |
| Thinking a `@Bean` method is a `FactoryBean` | Confusing a bean-creating method with the FactoryBean interface | Check whether the returned object implements the interface |
| Product is not ready at startup | FactoryBean usually creates the product on demand | Call where needed; use SmartFactoryBean if eager semantics are truly required |
| Testing the product via `new FactoryBean` gives a false integration pass | Fails to test Spring's dereferencing/caching | Add tests with a real ApplicationContext |
| Factory depends on too many business beans at context bootstrap | Triggers early initialization/circular dependency | Keep infrastructure factories lean and avoid side effects in `getObjectType()` |

## 18. When should you write your own FactoryBean?

FactoryBean is useful when a type of product needs a creation mechanism quite different from a normal bean definition, especially when the product:

- Is a **dynamic proxy** or an object requiring complex proxy configuration.
- Is created by a special SDK/runtime without a suitable constructor/factory method for direct registration.
- Has a stable interface type, but its implementation must be built from runtime metadata.
- Needs customization of how Spring sees the object type, singleton status, or lazy/eager product semantics.
- Is an infrastructure component that needs to be reused across many bean definitions.

However, if the problem is only **creating an HttpClient with a few configuration parameters**, a `@Bean` factory method is usually the more maintainable solution. If the problem is only **a singleton wanting a fresh prototype each time**, use `ObjectProvider<T>` or method injection instead of building a new FactoryBean unnecessarily.

Base the decision on the **container integration role** of `FactoryBean`, not merely because it has the word "factory" in its name.

## 19. Practical checklist

- Does the bean need custom creation, or is an ordinary `@Bean` method enough?
- Does the class actually `implements FactoryBean<Product>`?
- Does `getObjectType()` return an appropriate type with no side effects?
- Does `isSingleton()` match the product identity provided by `getObject()`?
- Is the factory bean definition scope singleton or prototype?
- Do you need the product `"name"` or the factory `"&name"`?
- Could Spring query the factory for its type before initialization finishes?
- Does the product have resources that need closing, and who owns that lifecycle?
- Is there concurrency when multiple threads look up the product?
- Is `SmartFactoryBean.isEagerInit()` needed, or is on-demand sufficient?
- Are unit tests of the factory and integration tests of the container separated?

## 20. Official documentation

- [Spring Framework Reference — Customizing Instantiation Logic with a FactoryBean](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html): the three FactoryBean methods and the `&beanName` syntax.
- [Spring Framework 6.2 Javadoc — FactoryBean](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/FactoryBean.html): the `getObject`, `getObjectType`, `isSingleton` contract and product/factory lifecycle.
- [Spring Framework 6.2 Javadoc — BeanFactory](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/BeanFactory.html): container API, `FACTORY_BEAN_PREFIX`, lookup, and scope queries.
- [Spring Framework 6.2 Javadoc — SmartFactoryBean](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/SmartFactoryBean.html): `isPrototype` and `isEagerInit` metadata.
- [Spring Framework Reference — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): singleton/prototype and lifecycle responsibilities.

**Model to remember:** `BeanFactory` is the **container**; `FactoryBean<T>` is **a special factory bean inside the container**; `getBean("x")` returns the **product** and `getBean("&x")` returns the **factory**. The factory's scope, the product's singleton status, and resource ownership are three things that must be evaluated separately.
