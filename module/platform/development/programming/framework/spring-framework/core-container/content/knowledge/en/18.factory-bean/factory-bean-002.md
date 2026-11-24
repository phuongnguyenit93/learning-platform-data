# Creating Products via FactoryBean.getObject in the Spring Framework Core Container

## 1. What is FactoryBean and why does it exist?

Normally, the Spring IoC Container creates a bean from a constructor or a `@Bean` method; the returned object is the bean the application uses. For some dependencies that are difficult to initialize—client SDKs, proxies, adapters, objects requiring multi-step configuration, or instances that must be created according to a special rule—Spring provides **`org.springframework.beans.factory.FactoryBean<T>`**.

`FactoryBean<T>` is **a bean that acts as a factory**. When the container is asked for a normal bean by the factory's name, Spring does not immediately return the factory, but instead calls **`getObject()` to obtain the *product* that the factory creates**. This is an extension point of the bean creation mechanism, not the `BeanFactory` interface.

Visual example:

```text
                       ApplicationContext
                               |
                        bean name: "formatter"
                               |
                       FormatterFactory
                    implements FactoryBean<Formatter>
                       /                  \
                      /                    \
getBean("formatter")                     getBean("&formatter")
        |                                       |
        v                                       v
 container uses getObject()              FormatterFactory itself
        |
        v
  Formatter (PRODUCT)
```

Two identities to distinguish:

- **Factory bean**: the `FormatterFactory` object that Spring creates, injects, and manages according to its bean definition.
- **Product**: the `Formatter` object that `getObject()` supplies to consumers.

This is why learners see a `@Bean` returning a `FactoryBean` yet calling `context.getBean("formatter")` returns an object of type `Formatter`, not `FormatterFactory`.

Importantly: `FactoryBean` is a **Spring API**, different from the *Factory Method* design pattern in plain Java. If you only have simple object-creation logic, a `@Bean` method returning the product directly is usually easier to understand and sufficient; you do not always need to write a `FactoryBean`.

## 2. The three core methods of FactoryBean<T>

In Spring Framework 6.x/7.x, the interface has three key methods (below is an **abbreviated signature**, not source code to copy verbatim):

```java
package org.springframework.beans.factory;

public interface FactoryBean<T> {
    T getObject() throws Exception;

    Class<?> getObjectType();

    default boolean isSingleton() {
        return true;
    }
}
```

Meaning table:

| Method | Contract | Design notes |
| --- | --- | --- |
| `T getObject()` | Provides a product instance, either shared or independent depending on the factory | May throw `Exception`, called by the container when the product is needed |
| `Class<?> getObjectType()` | Declares the product type; may return `null` if not yet known | Should return a stable type **without creating the product** |
| `boolean isSingleton()` | Indicates whether the factory supplies **the same stable object reference** | Defaults to `true`; must not declare true if it actually returns different objects |

### 2.1. getObject(): where the product is created or retrieved

`getObject()` can carry out the workflow: validate config → build structure → initialize SDK → equip proxy → return product. When the container receives a `getBean("name")` request, it uses the FactoryBean mechanism to retrieve the product from this method (or retrieve a cached singleton product).

```java
@Override
public Client getObject() throws Exception {
    Client client = Client.builder()
            .endpoint(endpoint)
            .credentials(credentials)
            .build();
    client.initialize();
    return client;
}
```

This is only **illustrative Java pseudocode**; `Client`/builder/fields are hypothetical APIs from another SDK, not part of Spring and not a standalone runnable example. It shows where custom product creation goes.

`getObject()` may be called **when the product is actually requested**, not necessarily right when Spring creates the factory bean. The fact that a singleton factory is pre-instantiated **does not mean** the product is always eagerly created. For ordinary factories, the product is usually created on demand; `SmartFactoryBean.isEagerInit()` can change this behavior for eligible beans.

### 2.2. getObjectType(): crucial for type discovery

Spring uses `getObjectType()` when resolving dependencies by type, `getType(name)`, `getBeansOfType(...)`, and other type-discovery operations.

```java
@Override
public Class<?> getObjectType() {
    return Client.class;
}
```

This is an illustrative fragment; `Client` must be the actual type published for the product. Keep in mind:
- It may be called **very early**, before the factory is fully initialized. Do not rely on fields that are only set in `@PostConstruct` if those fields might not be ready yet.
- Avoid creating connections, opening files, or calling `getObject()` just to guess the type; type discovery should ideally be lightweight and free of side effects.
- If it returns `null`, finding beans by product type may fail to detect the corresponding factory; Spring may skip that bean during type-based autowiring.
- Declare a type specific enough that the factory always returns; if the product has a proxy, return the interface type or a class that is actually assignable.
- Do not use `getObjectType()` to start up the product; that is the responsibility of `getObject()`.

### 2.3. isSingleton(): semantics of the *product*, not the factory bean

`isSingleton() == true` means the factory advertises **the product as a shareable/cacheable reference**. A Spring BeanFactory owning a singleton factory may cache the result from `getObject()` and return the same product on subsequent `getBean` calls.

`isSingleton() == false` means the product is not advertised as a singleton; Spring may call `getObject()` each time the product is requested. However, from `false` **you cannot conclude for sure that every product is completely independent**: a special factory might return objects shared via an external scope or pooling. `SmartFactoryBean.isPrototype()` provides stronger semantics about independent instances.

Two easily missed points:

1. The `FactoryBean` **itself** is usually declared as a singleton, while **its product** may be non-singleton. Those are two different scopes/contracts.
2. If declaring `isSingleton() == true`, the factory should always return **the same reference when `getObject()` is called directly**. Do not write `return new Product()` every time and rely solely on the container cache to mask a contract violation, especially if the factory is used outside the bean factory.

Example illustrating the difference:

```text
FactoryBean "sharedClient":
    factory scope = singleton
    isSingleton() = true
    getObject()   = same Client after creation
    getBean("sharedClient") multiple times -> one product reference

FactoryBean "freshClient":
    factory scope = singleton
    isSingleton() = false
    getObject()   = new Client each time
    getBean("freshClient") multiple times -> multiple product references

FactoryBean "otherFactory" (prototype):
    factory scope = prototype
    isSingleton() = true
    do not assume by default that all lookups share one container-wide factory/product
```

The prototype factory case should be examined separately, because the factory itself can be created anew each time; do not use `isSingleton()` alone to infer application-wide identity when the factory bean configuration is not singleton.

## 3. How does the container interpret bean names?

The special symbol **`&`** is `BeanFactory.FACTORY_BEAN_PREFIX`. It indicates how to dereference the **factory** instead of the product.

Suppose a bean named `"parser"` is a `FactoryBean<Parser>`:

```java
Parser p = context.getBean("parser", Parser.class);
FactoryBean<?> f = context.getBean("&parser", FactoryBean.class);
```

This code fragment assumes `context` is an `ApplicationContext` containing a bean named `parser`, and `Parser` is already defined. The first line requests the **product**; the second line requests the **FactoryBean** itself.

| Call | Normal result |
| --- | --- |
| `getBean("parser")` | Product of `FactoryBean.getObject()` |
| `getBean("&parser")` | The `FactoryBean` factory instance |
| `getBean("parser", Parser.class)` | Product of type `Parser` |
| `getBean("&parser", ParserFactory.class)` | Factory instance of type `ParserFactory` |
| `getType("parser")` | Product type from `getObjectType()` when determinable |
| `getType("&parser")` | Type of the factory |
| `getBeanNamesForType(Parser.class)` | May list bean names of products compatible with `Parser` |
| `getBeanNamesForType(FactoryBean.class)` | Queries factory types; details depend on configuration and type discovery |

**Do not write `getBean("parser")` and cast to `ParserFactory`**: the normal name returns the product, not the factory. Conversely, injecting the factory into a service instead of the product changes the service's contract and easily causes type errors.

`&` is a special syntax of Spring BeanFactory when **looking up beans by name**, not a Java reference operator, not a resource path prefix, and should not be confused with shell referencing semantics or XML entities.

### Does retrieving the factory cause the product to be created?

In the normal case, `getBean("&parser")` retrieves the factory without forcing `getObject()` to be called to create the product. However, the factory itself may perform initialization in its constructor/`@PostConstruct`, so **do not** assume retrieving the factory is guaranteed to be side-effect-free. Measure how many times `getObject()` is called if you need to determine when the product is created.

## 4. Spring's call flow when retrieving a product

Simplified operational model inside a BeanFactory:

```text
context.getBean("parser")
       |
       v
BeanFactory resolves bean definition "parser"
       |
       v
Get or create ParserFactory instance (factory bean)
       |
       +-- factory has been initialized according to the bean lifecycle
       |
       v
Identify: does instance implement FactoryBean<?> ?
       |
       +-- name starts with "&" -> return ParserFactory
       |
       +-- normal name:
                |
                +-- if singleton product is cached -> return cache
                |
                +-- if not present / not singleton:
                         +-- factory.getObject()
                         +-- process product via appropriate container mechanism
                         +-- cache if singleton product is eligible
                         +-- return product to caller
```

This is a conceptual description, not a verbatim copy of `AbstractBeanFactory`'s entire internal algorithm. When `getObjectType` is called, post-processor handling, circular dependencies, prototype `FactoryBean`s, and early references may vary depending on the bean type.

From this we can observe:
- `getBean("parser")` does not mean Java invokes the `Parser` constructor right on that line; it may have been created earlier or cached.
- A singleton factory can exist from startup while the product has not yet been requested.
- `BeanPostProcessor` applies to the factory bean as a Spring-created bean. Spring also has a mechanism for post-processing products from `FactoryBean`, but **do not assume the product goes through the exact same sequence of constructor injection, `@PostConstruct`, and destroy callbacks as a regular bean definition**. The factory often must take responsibility for its product's own init/cleanup when needed.
- When the product is a client with resources that must be closed, clearly design who owns the resource, when it closes, and how many users share the product.

## 5. Complete Spring Core, Java 17+ example: singleton and non-singleton products

The following sample is **runnable** with Java 17+, Maven 3.9+, and Spring Framework 6.2.18, without Spring Boot, a web server, or a database. There are **two singleton FactoryBeans** managing two different products:
- `sharedParser`: `isSingleton() == true`, the product is cached and the factory itself also guarantees returning the same reference.
- `freshParser`: `isSingleton() == false`, each `getObject()` in the example creates a different `Parser`.

When reading from the context, we see the normal name returns `Parser`, the name with `&` returns `ParserFactory`, and `getObjectType` enables type discovery before creating the product.

### 5.1. Project structure

```text
factorybean-demo/
├── pom.xml
└── src/main/java/edu/example/factorybean/
    ├── Parser.java
    ├── ParserFactory.java
    ├── AppConfig.java
    └── Main.java
```

**pom.xml**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>factorybean-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.18</version>
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
                <configuration>
                    <mainClass>edu.example.factorybean.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**src/main/java/edu/example/factorybean/Parser.java**

```java
package edu.example.factorybean;

// Immutable value object to identify each product.
public record Parser(String mode, int serial) {
    public String describe() {
        return mode + "#" + serial;
    }
}
```

**src/main/java/edu/example/factorybean/ParserFactory.java**

```java
package edu.example.factorybean;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.beans.factory.FactoryBean;

public final class ParserFactory implements FactoryBean<Parser> {
    private final String mode;
    private final boolean singletonProduct;
    private final AtomicInteger counter = new AtomicInteger();
    private Parser shared;

    public ParserFactory(String mode, boolean singletonProduct) {
        this.mode = mode;
        this.singletonProduct = singletonProduct;
    }

    @Override
    public synchronized Parser getObject() {
        if (singletonProduct) {
            if (shared == null) {
                shared = new Parser(mode, counter.incrementAndGet());
            }
            return shared;
        }
        return new Parser(mode, counter.incrementAndGet());
    }

    @Override
    public Class<?> getObjectType() {
        // Do not open resources or create Parser just to determine the type.
        return Parser.class;
    }

    @Override
    public boolean isSingleton() {
        return singletonProduct;
    }

    public int createdCount() {
        return counter.get();
    }
}
```

`ParserFactory` uses `synchronized getObject()` to guarantee that, even when the factory is called directly, the singleton case still creates only one product without races. `AtomicInteger` provides safe counting in tests; the example does not use a static counter, so two different factories each start from 1. With `isSingleton()==false`, two calls return two `record Parser` instances with different identities even if their data could be equal when a system produces the same values (in the example, serials do not repeat within the same factory).

**src/main/java/edu/example/factorybean/AppConfig.java**

```java
package edu.example.factorybean;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AppConfig {
    @Bean("sharedParser")
    public ParserFactory sharedParserFactory() {
        return new ParserFactory("shared", true);
    }

    @Bean("freshParser")
    public ParserFactory freshParserFactory() {
        return new ParserFactory("fresh", false);
    }
}
```

Both `@Bean` methods return `ParserFactory`, yet when the application asks for `sharedParser` or `freshParser`, Spring returns the **Parser product** rather than the factory. `proxyBeanMethods=false` does not disable `FactoryBean`: it only changes how Spring handles calls between `@Bean` methods inside the configuration class.

**src/main/java/edu/example/factorybean/Main.java**

```java
package edu.example.factorybean;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public final class Main {
    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            System.out.println("type via name: "
                    + context.getType("sharedParser").getSimpleName());
            System.out.println("type via &: "
                    + context.getType("&sharedParser").getSimpleName());

            Parser a = context.getBean("sharedParser", Parser.class);
            Parser b = context.getBean("sharedParser", Parser.class);
            ParserFactory sharedFactory =
                    context.getBean("&sharedParser", ParserFactory.class);

            System.out.println("shared same instance: " + (a == b));
            System.out.println("shared serial: " + a.serial());
            System.out.println("shared created: " + sharedFactory.createdCount());
            System.out.println("factory reference same: "
                    + (sharedFactory ==
                       context.getBean("&sharedParser", ParserFactory.class)));

            Parser x = context.getBean("freshParser", Parser.class);
            Parser y = context.getBean("freshParser", Parser.class);
            ParserFactory freshFactory =
                    context.getBean("&freshParser", ParserFactory.class);

            System.out.println("fresh same instance: " + (x == y));
            System.out.println("fresh serials: " + x.serial() + "," + y.serial());
            System.out.println("fresh created: " + freshFactory.createdCount());
        }
    }
}
```

In the directory containing `pom.xml`, run:

```bash
mvn -q compile exec:java
```

**Stdout lines printed by the program, in order:**

```text
type via name: Parser
type via &: ParserFactory
shared same instance: true
shared serial: 1
shared created: 1
factory reference same: true
fresh same instance: false
fresh serials: 1,2
fresh created: 2
```

Maven/Spring may produce different environment logging, but the `System.out.println` lines here have deterministic values per the sample configuration. No other singleton requests `Parser` before those lines. A normal `FactoryBean` product is not eagerly initialized just because the factory exists; calling `getType(...)` here does not create the product because `getObjectType()` purely returns `Parser.class`.

Because `sharedParser` advertises singleton, the container can cache the product from the first `getObject()` call; `ParserFactory` also always returns the same reference if called directly. Because `freshParser` does not advertise singleton, two `getBean(...)` calls delegate to the factory to create two new records with serials 1 and 2.

**Interesting experiment:** If you change `freshParser`'s `isSingleton()` to true while `getObject()` still creates a new product each time (removing the cache branch), you have written a factory that **violates the contract**. Spring may cache the product from the first call when the factory is a singleton, causing two `getBean` calls to still match, but you must not use accidental caching to conclude the factory is correct.

## 6. How do @Bean and FactoryBean differ?

Three ways of creating objects can coexist in Spring:

### 6.1. Ordinary @Bean

```java
@Configuration(proxyBeanMethods = false)
class BasicConfig {
    @Bean
    Parser parser() {
        return new Parser("direct", 1);
    }
}
```

This is a fragment requiring imports for `Configuration`, `Bean`, and this lesson's `Parser` type. When calling `getBean("parser")`, Spring returns the object from the `@Bean` method. No class implements `FactoryBean`; the product creation logic sits right inside the configuration method.

### 6.2. @Bean returning a FactoryBean

```java
@Configuration(proxyBeanMethods = false)
class AdvancedConfig {
    @Bean("parser")
    ParserFactory parserFactory() {
        return new ParserFactory("generated", true);
    }
}
```

A fragment similar to the sample project: when calling `getBean("parser")`, Spring applies the **FactoryBean contract** and returns `Parser`. Meanwhile `getBean("&parser")` is `ParserFactory`.

### 6.3. Factory method of a bean definition

In XML or a manually configured `BeanDefinition`, Spring can call a static/instance **factory method** specified via metadata to build the bean. This is the **factory-method mechanism**, which does not necessarily use the `FactoryBean` interface.

| Property | `@Bean` returning regular object | `@Bean` returning `FactoryBean<T>` | Bean definition factory method |
| --- | --- | --- | --- |
| Where is the product created? | Inside the `@Bean` method | Inside `FactoryBean.getObject()` | Inside the method per the bean definition |
| `getBean("name")` | Returns the instance created by the method | Returns the product `T` | Returns the factory method result |
| `getBean("&name")` | Not used if the bean is not a FactoryBean | Returns the factory instance | Meaningful only if the result is a FactoryBean |
| Uses `getObjectType()`, `isSingleton()`? | No | Yes | No, unless the result is a FactoryBean |
| Suitable for | Most simple dependencies | Complex instantiation logic, type metadata, and separate product scope | Specific factory-method configurations |

**Choose the simplest thing that meets the requirement.** `FactoryBean` is useful when you need to encapsulate a product creation mechanism with type/identity metadata; do not use it just to hide a few lines of `new SomeService()`.

## 7. Product and Factory have different lifecycles

### 7.1. Lifecycle of the factory bean

When Spring creates an instance of `ParserFactory` (via `@Bean` or another declaration), it can:
1. Call the constructor/factory method to create `ParserFactory`.
2. Inject dependencies into the factory instance (if the factory is configured for Spring injection).
3. Execute `Aware` callbacks, `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, or a custom init method on the **factory**.
4. Apply `BeanPostProcessor`s to the factory; register the factory's destruction callback if appropriate for its scope.

Because the factory is a Spring-managed bean, ordinary bean lifecycle rules apply **to the factory itself**.

### 7.2. When is the product created?

There is no single "always at refresh" answer:
- An eager singleton factory can be created at container refresh, yet the product is normally created by `getObject()` **on demand**.
- The product can be requested early when another singleton depends on the product type.
- A `SmartFactoryBean` can advertise `isEagerInit() == true`, causing Spring to initialize the singleton product early during pre-instantiation.
- If the product is already cached, another lookup does not necessarily call `getObject()` again.
- With a non-singleton factory or non-singleton product, the timing/count of creation depends on the number of resolutions and the factory's scope.

`SmartFactoryBean<T>` extends `FactoryBean<T>` with `isPrototype()` and `isEagerInit()`. It primarily serves complex infrastructure/frameworks; for ordinary applications, prefer the basic `FactoryBean<T>`.

### 7.3. The product does not automatically receive a full lifecycle like a separate bean definition

A product returned by `FactoryBean.getObject()` may have some `BeanPostProcessor`s applied by Spring at the product publishing step, but you must not infer that the object goes through the **full** constructor injection, `@PostConstruct`, `InitializingBean`, destroy methods, and all semantics of an independently declared bean.

Example:

```java
public final class SocketClient implements AutoCloseable {
    private boolean connected;

    public void connect() {
        connected = true;
    }

    @Override
    public void close() {
        connected = false;
    }
}
```

This is a syntactically standalone Java class, though it does not actually open a socket; it models a resource lifecycle. If the factory calls `new SocketClient()` and then `connect()` to return the product, you must specify who will call `close()`. One option is for the **factory** to implement `DisposableBean` and close the resource it created when the factory is destroyed.

```java
public final class ClientFactory
        implements FactoryBean<SocketClient>, DisposableBean {
    private SocketClient client;

    @Override
    public synchronized SocketClient getObject() {
        if (client == null) {
            client = new SocketClient();
            client.connect();
        }
        return client;
    }

    @Override
    public Class<?> getObjectType() {
        return SocketClient.class;
    }

    @Override
    public boolean isSingleton() {
        return true;
    }

    @Override
    public synchronized void destroy() {
        if (client != null) {
            client.close();
            client = null;
        }
    }
}
```

This factory snippet requires imports for `org.springframework.beans.factory.FactoryBean`, `DisposableBean`, and the `SocketClient` class in the same package; it does **not** belong to the runnable sample in section 5. This cleanup approach works when the factory is managed/destroyed by Spring in the appropriate scope and the app does not continue using the client after shutdown. For non-singleton products, the factory must track the instances needing closing or hand cleanup responsibility to the caller/another scope; it cannot simply hold a single `client` field.

### 7.4. Do not mix the FactoryBean product concept with @Scope("prototype")

`FactoryBean.isSingleton() == false` is not completely equivalent to the `prototype` bean definition scope. A non-singleton `FactoryBean` implementation may use pooling or a custom scope; `SmartFactoryBean.isPrototype()` distinguishes products that are **independent each time**. In the `freshParser` example, the product is genuinely new each time because the `getObject()` code itself creates `new Parser`.

`context.isSingleton("factoryName")`/`isPrototype("factoryName")` queries the bean name according to BeanFactory logic, which can reflect product semantics; `context.isSingleton("&factoryName")` queries factory semantics. When in doubt, check both the bean definition scope and `FactoryBean.isSingleton()`, rather than concluding from method names alone.

## 8. Type discovery, autowiring, and common pitfalls

### 8.1. getObjectType() returning null makes the bean hard to inject

When searching for a product by type, Spring may ask the factory what type it creates **without calling getObject()**. If `getObjectType()` returns `null`, a `Parser` dependency might not match or be discovered during autowiring.

```java
@Override
public Class<?> getObjectType() {
    return null; // Only use when type truly cannot be known early.
}
```

This is an anti-pattern fragment. It is better to declare `Parser.class` or an appropriate `ParserContract.class` interface right from constructor/config metadata. Do not run expensive SDK initialization inside `getObjectType()`.

### 8.2. Multiple products of the same type cause ambiguous dependencies

In section 5, two factories both create `Parser`. If you write:

```java
@Service
class ParserConsumer {
    private final Parser parser;

    ParserConsumer(Parser parser) {
        this.parser = parser;
    }
}
```

This snippet needs an import for `org.springframework.stereotype.Service` and the `Parser` type in the same package. If there are two product beans `sharedParser` and `freshParser`, injecting `Parser` **without a qualifier** can throw `NoUniqueBeanDefinitionException` because there are multiple candidates of the same type. Use:

```java
@Service
class ParserConsumer {
    private final Parser parser;

    ParserConsumer(@Qualifier("sharedParser") Parser parser) {
        this.parser = parser;
    }
}
```

Requires imports for `Service` and `Qualifier`; `@Qualifier` selects the `sharedParser` product bean. Do not inject by `ParserFactory` if the goal is the product. With the special factory name, `getBean("&sharedParser")` is always clear when the factory itself is needed for infrastructure.

### 8.3. Generic type metadata

Implementing `FactoryBean<Parser>` helps Java type safety and also helps Spring infer the type in some cases. However, you should still implement `getObjectType()` accurately; the generic signature does not completely replace the responsibility of declaring the product type, especially for factories that build objects based on config. With `@Bean` methods returning `FactoryBean<Parser>` directly instead of the concrete implementation, check actual type discovery and registration if infrastructure depends on it.

### 8.4. Retrieving the factory with & and calling getObject() directly

`getBean("&sharedParser")` only requests the factory. If you call `sharedFactory.getObject()` yourself, you bypass **part** of Spring's behavior when retrieving the product, such as caching and some post-processing; the factory should still satisfy the `isSingleton()` contract. Therefore ordinary consumers should receive `Parser` from Spring rather than calling the factory directly, unless you are building infrastructure that needs control over the factory.

### 8.5. getObjectType should not force early initialization

An incorrect implementation:

```java
@Override
public Class<?> getObjectType() {
    return getObject().getClass(); // Creates product just to know the type!
}
```

This is an anti-pattern fragment, which may not even compile if `getObject()` throws a checked `Exception`. It can open connections right during type matching, slow down startup, create circular dependencies, and increase side effects. Declare a static type whenever possible or a type estimate that causes no side effects.

## 9. Exceptions and uninitialized state

`FactoryBean.getObject()` can throw `Exception`. When invoked through Spring's `getBean(...)`, errors may be wrapped into a bean creation exception, depending on the error type and phase. Do not treat an exception as a promise that the container will automatically retry and roll everything back.

```java
@Override
public Client getObject() throws Exception {
    if (!configured) {
        throw new FactoryBeanNotInitializedException(
                "ClientFactory has not finished configuration");
    }
    return createClient();
}
```

The snippet needs `Client`, `FactoryBeanNotInitializedException`, the `configured` field, and the `createClient` method belonging to the application; it is illustrative only and **not standalone runnable**. In Spring, `FactoryBeanNotInitializedException` is the way to report that the factory cannot supply the product yet, for example when the factory is requested early due to a circular dependency.

Rules to remember:
- Do not retrieve the factory's own product inside its constructor/`@PostConstruct` and create a `getBean("self")` cycle.
- Do not perform unbounded network I/O inside `getObject()`. Use clear timeouts and error policies to avoid hanging requests or container startup.
- If creating the product opens resources and then fails, clean up what was already opened right in `catch/finally`; do not rely on every destroy callback running after a failed initialization.
- If you want to retry factory product creation, you must define when to retry and when to cache exceptions or fall back; retry semantics are not automatically imposed by `FactoryBean`.
- Do not expose tokens, passwords, or sensitive URLs in exception messages/logs when SDK initialization fails.

## 10. FactoryBean, ObjectFactory, ObjectProvider, and BeanFactory

Four interfaces have similar names but different responsibilities:

| API | Who implements/primarily uses it? | Role |
| --- | --- | --- |
| `FactoryBean<T>` | A Spring bean acting as a factory | Integrates product creation logic with the container, along with type/singleton metadata |
| `BeanFactory` | The container | Stores/resolves bean definitions and supplies instances |
| `ObjectFactory<T>` | Simple provider abstraction | Retrieves an object via `getObject()` when needed, without FactoryBean's product type/singleton contract |
| `ObjectProvider<T>` | Container injection/lookup | Retrieves beans on demand, with optional access and utilities like `getIfAvailable()`, `stream()` |

`FactoryBean` is **not** a `BeanFactory`, and calling `ObjectProvider.getObject()` does **not** mean the provider class is creating the bean via a `FactoryBean`. A provider can resolve a bean managed normally by Spring or supplied by a FactoryBean—the two mechanisms are independent.

When to choose which tool?

- Want Spring to register **a product type with complex instantiation logic** and have the bean name behave as the product → `FactoryBean<T>`.
- Want a prototype dependency each time business logic runs (already declared as a prototype bean) → inject `ObjectProvider<T>` and call `getObject()` when needed.
- Want to create an object with simple one-time configuration → `@Bean`.
- Want dynamic bean-name lookup inside a framework → `BeanFactory`/`ApplicationContext`, while limiting service-locator usage in business code.

## 11. Concurrency and caching: whose responsibility is it?

If a `FactoryBean` supplies a singleton product to multiple threads, Spring can cache one reference within a BeanFactory. **Singleton identity does not mean thread safety**. The product must manage its own mutable state and corresponding invariants; the factory can also receive multiple calls if the product is non-singleton and accessed concurrently.

In the `ParserFactory` example:
- `getObject()` has `synchronized` to preserve the singleton product invariant and serial counter, even if someone outside the container calls it directly.
- `Parser` is a Java record with two immutable fields (`String` and primitive `int`) and no mutable state.
- `isSingleton()` does not use a mutable variable that changes at runtime; it is fixed from the constructor.
- `getObjectType()` purely returns `Parser.class`, making it safe when the container queries it repeatedly.

A production client-producing factory also needs:
1. Thread-safe lazy initialization or clearly ordered eager construction.
2. Cleanup mechanisms whether startup succeeds or fails.
3. A share/pool/tenant policy for the product aligned with `isSingleton()`.
4. Not leaking per-user request state through a singleton product.
5. If deployed across multiple pods, not treating a singleton as cluster-wide unique.
6. Caching singleton products only per container/scope, without turning into an uncontrolled process-global cache.

Do not set `isSingleton=false` while internally creating a bounded pool and advertising "an independent prototype every time" to downstream code. In reality, the contract only says the product is non-singleton; if independence is mandatory, design/verify identity and `SmartFactoryBean.isPrototype()` when truly needed.

## 12. Common mistakes and how to fix them

| Mistake / symptom | Cause | How to fix |
| --- | --- | --- |
| `getBean("myFactory")` returns the product instead of the factory | Spring dereferences `FactoryBean` for a normal name | Use `getBean("&myFactory")` to retrieve the factory |
| `ClassCastException` when casting product to FactoryBean | Confusing the two layers of objects | Use type `T` for the product and `FactoryBean<T>` for the factory |
| Same bean name yet `getType` returns an unexpected type | Product type is advertised via `getObjectType()` | Check the product type and the `&` prefix |
| Injecting the product by type fails to find it | `getObjectType()` returns `null`/wrong type | Return a stable type that can be determined early |
| `getObject()` runs during type discovery | `getObjectType()` is written to call `getObject()` | Separate type discovery logic from object creation |
| `isSingleton()==true` yet calling the factory directly returns different instances | Factory violates the contract | Cache the reference or change `isSingleton` accordingly |
| Singleton factory yet the product appears multiple times | `isSingleton()==false` or the factory creates products itself | Distinguish factory scope from product identity |
| Two products of the same type make injection ambiguous | Multiple bean candidates | Use `@Qualifier` or mark a primary bean by design |
| Product holds resources that are never closed | Product lifecycle is not a standalone bean definition | Have the factory manage cleanup or create a separate lifecycle component |
| `@PostConstruct` on the product does not run as expected | The product does not receive the full lifecycle of a normally declared bean | Initialize in the factory or register appropriate callbacks |
| Circular dependency initialization error | Factory/product requests itself or an unready dependency | Design an acyclic dependency graph and defer lookup when appropriate |
| `getObject()` blocks startup for a long time | Heavy I/O, missing timeouts | Add timeouts, retry policies, and proper lifecycle/readiness handling |
| Product looks like a singleton yet is not thread-safe | Same instance used by multiple threads | Design immutability, synchronization/atomics per invariants |
| Wanting one product per request while factory caches a singleton | Wrong scope semantics used | Use request scope or proper factory logic instead of toggling flags randomly |
| Retrieving `&factory` yet the product is not created | `&` returns the factory, without forcing `getObject` | Call `getBean` without the prefix when you actually need the product |

## 13. Practice and self-assessment questions

**Exercise A — SDK client:** A configuration creates a client wired with an endpoint, retry policy, and credential provider; the client is thread-safe to share and expensive to create. Choose `isSingleton=true`, cache one reference, and clean up when the container closes. `getObjectType` should return the exact client class/interface without opening a connection just to infer the type.

**Exercise B — per-task formatter:** Each task needs stateful data accumulation and cannot be shared. You can use `FactoryBean<Formatter>` with `isSingleton=false` where each `getObject()` returns a new instance; however, if called multiple times within the same task, you must keep the product already retrieved instead of calling the provider again and accidentally creating another instance.

**Exercise C — integrating a legacy factory:** A third-party API provides a very long static factory method and exposes no constructor. If the logic to create one object is simple, a `@Bean` calling the static method suffices. If you also need product type discovery, a non-singleton creation policy, or reuse across multiple configuration styles, `FactoryBean` is worth considering.

Questions:
1. How does Spring `FactoryBean<T>` differ from `BeanFactory`?
2. If bean name `paymentClient` is a `FactoryBean<Client>`, what does `getBean("paymentClient")` return?
3. How do you retrieve the factory itself of `paymentClient`?
4. When `isSingleton()==true`, what must the factory guarantee about the reference returned from `getObject()`?
5. Does a singleton factory bean definition force the product to be a singleton?
6. Is a non-singleton product guaranteed to be an independent instance on every lookup?
7. Why should `getObjectType()` work before initialization and without calling `getObject()`?
8. If `getObjectType()` returns null, how can type-based autowiring be affected?
9. There are two FactoryBeans both returning `Parser`. What error can injecting `Parser` without a qualifier cause?
10. What is `SmartFactoryBean.isEagerInit()` used to distinguish?
11. Does a product created by `getObject()` automatically receive all `@PostConstruct`/destroy callbacks like a separate bean definition?
12. A singleton product has methods called concurrently by multiple requests. Does `isSingleton()` guarantee it is thread-safe?
13. Why should you use `&` when wanting to count how many times the factory created a product?
14. When a factory's `getObject()` itself calls `context.getBean("sameName")`, what risk can occur?
15. If you only have `return new Parser("A", 1)`, why is `@Bean` usually more suitable than `FactoryBean`?

**Suggested answers:** (1) FactoryBean creates a product, BeanFactory is the container. (2) The `Client` product. (3) `getBean("&paymentClient")`. (4) Return the same shared reference; the container may cache it. (5) No, the product's `isSingleton` is independent. (6) Not necessarily; `isSingleton=false` only says non-singleton, while `SmartFactoryBean.isPrototype` is more explicit. (7) Type matching can occur early; creating the product then causes side effects/cycles. (8) The candidate may not be discovered. (9) `NoUniqueBeanDefinitionException`. (10) Whether the singleton product needs to be eagerly created at bootstrap. (11) Not automatically. (12) No. (13) To obtain the factory itself instead of the product and inspect its metadata/counter. (14) Circular dependency or recursive creation. (15) Less boilerplate, sufficient for simple objects.

## 14. Production application checklist

1. The bean name is used to retrieve the product, while the factory must be explicitly retrieved with `&` when truly needed.
2. `getObjectType()` is accurate, lightweight, stable, and does not require the product to already be created.
3. `isSingleton()` accurately reflects the reference-sharing capability of `getObject()`.
4. If the product is a singleton, the factory does not return a new instance each time when called directly.
5. If the product is non-singleton, consumers know when to hold onto one instance across multiple processing steps.
6. Do not use `@Scope("prototype")` on the factory as a substitute for designing the product lifecycle.
7. Avoid circular dependencies and do not resolve the factory's own product during factory initialization.
8. Client/connection resources have an owner responsible for closing them, even when initialization fails.
9. Code does not assume the product automatically goes through the entire lifecycle of a separate bean definition.
10. Shared products are thread-safe per business requirements, not merely because `isSingleton=true`.
11. Type-based injection handles cases with multiple candidates explicitly.
12. Add tests for product identity, type queries without object creation, failure paths, and cleanup.
13. For factories using external SDKs, measure `getObject()` latency and configure timeouts/backoff.
14. Do not treat a per-container singleton as a JVM-wide or cluster-wide singleton.

## Official documentation

- Spring Framework Reference — Customizing Instantiation Logic with a FactoryBean: https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html
- Spring Framework 6.2 — `FactoryBean` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/FactoryBean.html
- Spring Framework 6.2 — `BeanFactory` Javadoc and `FACTORY_BEAN_PREFIX`: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/BeanFactory.html
- Spring Framework 6.2 — `SmartFactoryBean` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/SmartFactoryBean.html
- Spring Framework Reference — Bean Scopes: https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html
- Spring Framework Reference — Java-based Container Configuration (`@Bean`): https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html
