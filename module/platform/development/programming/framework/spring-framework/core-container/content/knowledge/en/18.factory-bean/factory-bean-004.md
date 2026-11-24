# Meaning of `isSingleton()` for Products Created by a FactoryBean

## 1. The problem to understand: a FactoryBean involves two different "objects"

In the Spring Core Container, `FactoryBean<T>` is not just an ordinary bean with an object-creation method. It is a **container extension point**: when Spring sees a bean implementing `FactoryBean`, retrieving the bean by its normal name returns **the factory's product** via `getObject()`, rather than returning the factory itself.

This creates two objects that must be distinguished:

1. **FactoryBean instance:** the Java object implementing `org.springframework.beans.factory.FactoryBean<T>`, created and managed by Spring as a bean definition.
2. **Product instance:** the object of type `T` returned by the factory from `getObject()`, which Spring may cache and supply elsewhere in the application.

The `isSingleton()` method of `FactoryBean` answers the question:

> **Is the product exposed by the factory a shared object that BeanFactory can cache and reuse?**

It does **not** by itself declare the scope of the **FactoryBean instance**. The factory can be a singleton while the product is non-singleton. Likewise, looking only at `FactoryBean.isSingleton() == true` is not enough to conclude the product is a singleton across all lookups if the factory bean itself is configured as prototype.

This is the central distinction of this lesson.

### Learning objectives

After this lesson you will be able to:

- Distinguish a `FactoryBean` from the `getObject()` product object.
- Correctly explain `FactoryBean.isSingleton()`, its default value, and the container's caching mechanism.
- Compare the scope of the factory bean definition with the singleton/non-singleton status of the product.
- Understand why `false` **does not necessarily equate to an independent prototype instance**.
- Use `SmartFactoryBean.isPrototype()` and `BeanFactory.isPrototype(name)` when prototype semantics are needed.
- Know `getBean("name")` versus `getBean("&name")`, as well as how to check `isSingleton` for each name.
- Run a Spring Context 6.1.x, Java 17 example to demonstrate identity and the number of times `getObject()` is called.
- Avoid bugs from misdeclaring `isSingleton()` when the product has mutable state, holds resources, or needs to be created fresh per task.

## 2. The contract of `FactoryBean<T>`

The interface resides in package `org.springframework.beans.factory`.

~~~java
import org.springframework.beans.factory.FactoryBean;

// Abbreviated API signature for explanation; no need to redefine yourself.
public interface FactoryBean<T> {
    T getObject() throws Exception;

    Class<?> getObjectType();

    default boolean isSingleton() {
        return true;
    }
}
~~~

Three methods to understand individually:

| Method | What does it ask? | Responsibility |
| --- | --- | --- |
| `getObject()` | Which object is exposed as the product? | Creates or returns a product instance conforming to the contract |
| `getObjectType()` | What type does the product have? | Gives the container a basis for type recognition without creating the product first |
| `isSingleton()` | Can the product be shared as a singleton? | Returns `true` only when the exposed product is consistently the same cacheable reference |

In Spring Framework 6.1, `isSingleton()` has a **default implementation returning `true`**. You can override it to return `false` when the product is not a shared singleton.

`FactoryBean<T>` is a special Spring abstraction, **different** from the `BeanFactory` interface. Swapping the two words changes the entire meaning:

- `BeanFactory` is the **container interface**, having `getBean(name)`, `isSingleton(name)`, `isPrototype(name)`, etc.
- `FactoryBean<T>` is a **container-managed factory object** that produces/exposes a product `T`.

Also do not confuse `FactoryBean<T>` with the `@Bean` annotation: `@Bean` marks a Java factory method that creates a bean definition; a `@Bean` method may return an object implementing `FactoryBean<T>`, in which case Spring proceeds to specially handle the factory's product.

## 3. Looking by name: `name` is the product, `&name` is the factory

If you register a `FactoryBean<Product>` under the name `productFactory`:

~~~java
Object product = context.getBean("productFactory");

Object factory = context.getBean("&productFactory");
~~~

This is an illustrative snippet in a Spring application with a `productFactory` bean definition implementing `FactoryBean`.

- `getBean("productFactory")` retrieves the **product** exposed by `getObject()`.
- `getBean("&productFactory")` retrieves the **FactoryBean instance itself**.
- The `&` sign is Spring's **factory dereference prefix**, not a Java operator and does not change the actual bean definition name.
- The registered name of the factory bean remains `productFactory`; the `&productFactory` notation is used in certain lookup APIs to explicitly state "return the factory instead of the product".

### Two methods with the same name but different subjects

~~~java
factoryBean.isSingleton();      // Queries the product managed by the factory.
context.isSingleton("productFactory");  // Queries the object exposed under the product name.
context.isSingleton("&productFactory"); // Queries the factory instance itself.
~~~

Three related questions that **must not be conflated**:

- `FactoryBean.isSingleton()` belongs to the **product** contract.
- `BeanFactory.isSingleton("productFactory")` describes **lookup semantics under the product name**.
- `BeanFactory.isSingleton("&productFactory")` describes the **factory object** looked up via the `&` prefix.

In the common configuration where the factory bean itself is a singleton, the first two results will align. The result for `&name` can differ completely if the factory returns non-singleton products.

## 4. `isSingleton() == true`: declaring a shared product

A factory returning `true` means `getObject()` is declared to return **the same object reference**—a reference that the container can cache.

~~~java
public final class SharedClientFactory implements FactoryBean<Client> {
    private final Client shared = new Client();

    @Override
    public Client getObject() {
        return shared;
    }

    @Override
    public Class<?> getObjectType() {
        return Client.class;
    }

    @Override
    public boolean isSingleton() {
        return true;
    }
}
~~~

This is an illustrative class; it requires importing `FactoryBean` and defining `Client`.

If the factory bean is registered as a singleton in its bean definition, Spring can cache the object returned by `getObject()`. Two calls to `context.getBean("sharedClient")` normally return the same reference.

Important: **caching is an optimization/enforcement mechanism for BeanFactory lookup semantics, not a promise that Spring will call `getObject()` upfront or exactly once in all scenarios**. The Javadoc states the product **may be cached**; the implementation must remain valid even when Spring decides when to invoke it on demand.

A factory declaring singleton must be designed so that:

- `getObject()` returns a stable shared object.
- It does not create a new product on each call while hoping the container always masks that bug with caching.
- If lazily initialized, it uses synchronization or appropriate safe publication techniques.
- If the product has mutable state, sharing across multiple beans/threads is an intentional, considered choice.
- If the product holds resources that must be closed, ownership and lifecycle are explicitly designed.

### Default value

In Spring 6.1, if you **do not override `isSingleton()`**, the default is `true`. Therefore, a factory returning a new product on every `getObject()` without overriding `isSingleton()` can cause the container to cache the first product and reuse it unexpectedly.

This is a subtle bug: the source code of `getObject()` looks like it always does `new Product()`, yet callers of `getBean("name")` see the same instance.

## 5. `isSingleton() == false`: the product is not a shared singleton

A factory can supply new objects when requested:

~~~java
public final class NewSessionFactory implements FactoryBean<Session> {

    @Override
    public Session getObject() {
        return new Session();
    }

    @Override
    public Class<?> getObjectType() {
        return Session.class;
    }

    @Override
    public boolean isSingleton() {
        return false;
    }
}
~~~

This is an illustrative class requiring a `Session` definition.

When Spring sees `isSingleton() == false`, it does not use the same singleton product caching mechanism for that factory. Thus with an implementation returning `new Session()`, each product lookup through Spring receives a separate object.

**However, the subtlety per the Javadoc:** `isSingleton() == false` **does not by itself guarantee that products are independent instances**. It only states that the product is not a shared singleton cacheable under this contract. A factory may expose objects according to **another scope** (such as an object tied to a thread/request or a custom sharing mechanism).

If the semantics require **a fresh independent instance on every retrieval**, you must check the `getObject()` implementation, scope configuration, and the `SmartFactoryBean.isPrototype()` extension interface where appropriate. Do not simply equate "false = prototype".

### Two contrasting illustrations

A factory returning `false` and creating a new object:

~~~java
@Override
public Product getObject() {
    return new Product();
}
~~~

A factory also returning `false` but picking an object from per-request storage:

~~~java
@Override
public Product getObject() {
    return requestLocalProduct.get();
}
~~~

The two methods above are **illustrative snippets** only, not two methods placed in the same class. The second case can return the same object within the same request and different objects across requests. `isSingleton() == false` fits because the object is not a single shared singleton across all lookups, yet that does not mean every call within the same request is independent. The implementation must have its own valid context/storage.

## 6. Distinguishing 2 axes: FactoryBean scope and product scope

In the FactoryBean model, you must examine **two axes**:

1. Bean definition scope of the **factory**: singleton/prototype or another scope decided by the container.
2. Product semantics expressed by **FactoryBean.isSingleton()** and `getObject()` behavior.

With a singleton factory:

| FactoryBean scope | Product `isSingleton()` | Lookup by `name` | Lookup by `&name` |
| --- | --- | --- | --- |
| singleton | `true` | Shared/potentially cached product | Same factory instance |
| singleton | `false` | Not cached as a singleton product; result depends on `getObject()` | Same factory instance |
| prototype | `true` | Each lookup can create a new factory; **no guarantee of one global product** just because each factory returns true | New factory instance each time |
| prototype | `false` | Each lookup can create a new factory and products created by that factory | New factory instance each time |

**Key takeaway:** If you want a genuinely shared product, the simplest and most common approach is to give the `FactoryBean` itself singleton scope **and** declare `isSingleton() == true`, while ensuring `getObject()` exposes the same reference.

If the factory definition is prototype while `isSingleton()` returns true, each factory instance may create/supply its own product. "True" here still only describes the semantics **of the single factory being queried**, without creating a global object shared across different factory instances.

### Why understand the two axes independently?

If you only read:

~~~java
@Scope("prototype")
@Component
public class ClientFactory implements FactoryBean<Client> {
    @Override
    public boolean isSingleton() {
        return true;
    }

    // ...
}
~~~

you might mistakenly think `true` forces Spring to always expose the same client across the whole JVM. Wrong: a **prototype** factory is created anew for each lookup, unless something else retains and reuses a specific factory instance. Each factory can hold its own client.

The class snippet above is illustrative and does not compile standalone because it lacks `getObject()`, `getObjectType()`, and the required imports.

## 7. Complete Java 17 + Spring Context 6.1 example

The following example creates two singleton `FactoryBean`s:

- `SharedProductFactory`: always exposes the same product, `isSingleton() == true`.
- `FreshProductFactory`: creates a new product on each `getObject()`, `isSingleton() == false`.

It then checks object identity, factory identity, `getObject()` invocation counts, and `context.isSingleton(...)` results.

### 7.1. Structure

~~~text
factorybean-product-demo/
├── pom.xml
└── src/main/java/com/example/factory/FactoryBeanProductDemo.java
~~~

### 7.2. File `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>factorybean-product-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.13</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>com.example.factory.FactoryBeanProductDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.3. File `FactoryBeanProductDemo.java`

~~~java
package com.example.factory;

import org.springframework.beans.factory.FactoryBean;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class FactoryBeanProductDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            Product shared1 = context.getBean("sharedProduct", Product.class);
            Product shared2 = context.getBean("sharedProduct", Product.class);

            Product fresh1 = context.getBean("freshProduct", Product.class);
            Product fresh2 = context.getBean("freshProduct", Product.class);

            SharedProductFactory sharedFactory =
                    context.getBean("&sharedProduct", SharedProductFactory.class);
            FreshProductFactory freshFactory =
                    context.getBean("&freshProduct", FreshProductFactory.class);

            System.out.println("shared references equal: " + (shared1 == shared2));
            System.out.println("fresh references equal: " + (fresh1 == fresh2));
            System.out.println("shared product value: " + shared1.value());
            System.out.println("fresh product values: "
                    + fresh1.value() + ", " + fresh2.value());

            System.out.println("shared getObject calls: " + sharedFactory.calls());
            System.out.println("fresh getObject calls: " + freshFactory.calls());

            System.out.println("shared product isSingleton: "
                    + context.isSingleton("sharedProduct"));
            System.out.println("fresh product isSingleton: "
                    + context.isSingleton("freshProduct"));
            System.out.println("fresh factory isSingleton: "
                    + context.isSingleton("&freshProduct"));

            System.out.println("same fresh factory: "
                    + (freshFactory == context.getBean("&freshProduct")));
        }
    }

    public record Product(String value) {}

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean(name = "sharedProduct")
        public SharedProductFactory sharedProduct() {
            return new SharedProductFactory();
        }

        @Bean(name = "freshProduct")
        public FreshProductFactory freshProduct() {
            return new FreshProductFactory();
        }
    }

    public static class SharedProductFactory implements FactoryBean<Product> {
        private final Product shared = new Product("shared");
        private int calls;

        @Override
        public Product getObject() {
            calls++;
            return shared;
        }

        @Override
        public Class<?> getObjectType() {
            return Product.class;
        }

        @Override
        public boolean isSingleton() {
            return true;
        }

        public int calls() {
            return calls;
        }
    }

    public static class FreshProductFactory implements FactoryBean<Product> {
        private int calls;

        @Override
        public Product getObject() {
            calls++;
            return new Product("fresh-" + calls);
        }

        @Override
        public Class<?> getObjectType() {
            return Product.class;
        }

        @Override
        public boolean isSingleton() {
            return false;
        }

        public int calls() {
            return calls;
        }
    }
}
~~~

The code uses Java 17 `record Product`, with no database, network, or manually created threads. Both factory classes are `static` nested classes registered via `@Bean`. Component scanning is unnecessary because `AnnotationConfigApplicationContext(Config.class)` directly loads the configuration class.

The `calls` variables are simple counters, suitable **only for single-threaded demonstration**. If using a factory in a concurrent environment, design initialization/counters/resource writes with appropriate thread safety, such as `AtomicInteger` or synchronization.

### 7.4. Running

In the directory containing `pom.xml`, using JDK 17+ and Maven 3.9+:

~~~bash
mvn -q compile exec:java
~~~

The `System.out.println` lines actively printed by the application with Spring Context 6.1.13:

~~~text
shared references equal: true
fresh references equal: false
shared product value: shared
fresh product values: fresh-1, fresh-2
shared getObject calls: 1
fresh getObject calls: 2
shared product isSingleton: true
fresh product isSingleton: false
fresh factory isSingleton: true
same fresh factory: true
~~~

Maven and the logging framework may print additional information; above is only the example code's stdout. The result illustrates the standard caching mechanism for a singleton FactoryBean after two product lookups, without claiming that every framework, scope, or type-query path calls `getObject()` exactly once in all situations.

### 7.5. Analyzing the results

**`shared references equal: true`**: both `sharedProduct` lookups receive the same Product reference. The factory reports `isSingleton() == true` and returns the same `shared` object.

**`shared getObject calls: 1`**: in the illustrative run, the container caches the product after the first lookup; the second comes from cache. Note the condition that the factory bean itself is a singleton.

**`fresh references equal: false`**: `FreshProductFactory` reports `false`, so the product does not use singleton caching; the method returns `new Product(...)` each time.

**`fresh getObject calls: 2`**: two product lookups trigger two calls to `getObject()`. The same factory instance can create multiple products.

**`fresh factory isSingleton: true`**: `FreshProductFactory` itself is declared by a default singleton `@Bean`. This **does not contradict** the `freshProduct` product reporting non-singleton.

**`same fresh factory: true`**: retrieving `&freshProduct` twice returns the same factory object; the `&` sign does not create a new factory.

This is the clearest illustration of the rule:

> **A singleton FactoryBean can still supply a new product for each product lookup.**

## 8. Using `BeanFactory.isSingleton(name)` and `isPrototype(name)`

When querying state through the container, remember to pass the right name:

~~~java
context.isSingleton("sharedProduct");  // true  — shared product.
context.isSingleton("freshProduct");   // false — non-singleton product.
context.isSingleton("&freshProduct");  // true  — singleton factory.
~~~

This snippet can be placed in `main` of the section 7 example.

`BeanFactory.isSingleton(String name)` tells whether `getBean(name)` returns **the same shared singleton instance**. It examines the semantics of the **object looked up by name**, including when the name points to a FactoryBean product.

`BeanFactory.isPrototype(String name)` checks the semantics of receiving **independent instances**. According to the Javadoc, `isSingleton(name) == false` does not prove `isPrototype(name) == true` in every case: a scoped object can be neither singleton nor prototype.

For a plain `FactoryBean` not implementing `SmartFactoryBean`, Spring may treat `isSingleton() == false` as a prototype product signal when answering `isPrototype(name)` (per its documented contract), **but the implementation itself must guarantee the semantics it promises**. If the factory uses a custom scope and does not return independent instances, review the metadata carefully to avoid misleading the container and callers.

### Do not confuse with `FactoryBean.isSingleton()` of the factory instance

~~~java
FreshProductFactory f =
    context.getBean("&freshProduct", FreshProductFactory.class);

System.out.println(f.isSingleton());                   // false
System.out.println(context.isSingleton("&freshProduct")); // true
~~~

Two different values are **correct**, not a bug:

- `f.isSingleton()` asks about the **product**.
- `context.isSingleton("&freshProduct")` asks about the **factory object**.

## 9. `SmartFactoryBean.isPrototype()`: when confirming independent instances is needed

Spring has the extension interface `org.springframework.beans.factory.SmartFactoryBean<T>` adding metadata such as:

- `isPrototype()`: returns `true` when `getObject()` always supplies **independent instances**.
- `isEagerInit()`: hints that the factory and singleton product need to be initialized eagerly.

`SmartFactoryBean.isPrototype()` is **not the simple negation** of `FactoryBean.isSingleton()`.

Examples of semantics to distinguish:

| Product | `isSingleton()` | `SmartFactoryBean.isPrototype()` |
| --- | --- | --- |
| A fixed shared object | `true` | `false` |
| A new, independent object for each lookup | `false` | `true` |
| An object shared within request/session scope, distinct outside that scope | `false` | `false` |

The table illustrates contract relationships; a custom factory must itself implement behavior consistent with reality.

`SmartFactoryBean.isPrototype()` returns `false` by default, because you cannot deduce that a product is an independent instance merely from its not being a singleton. If the implementation guarantees a fresh independent instance each time, it can override to `true`.

Be careful: `SmartFactoryBean` is meant for **infrastructure metadata when truly needed**. For a simple factory returning a shared object, a plain `FactoryBean` suffices.

### Illustrating `SmartFactoryBean`

~~~java
import org.springframework.beans.factory.SmartFactoryBean;

public class TaskFactory implements SmartFactoryBean<Task> {
    @Override
    public Task getObject() {
        return new Task();
    }

    @Override
    public Class<?> getObjectType() {
        return Task.class;
    }

    @Override
    public boolean isSingleton() {
        return false;
    }

    @Override
    public boolean isPrototype() {
        return true;
    }
}
~~~

This is an illustrative class requiring a `Task` definition and registering `TaskFactory` as a bean. It explicitly declares that each `getObject()` creates an independent target. Do not put `true` in `isPrototype()` when the method actually returns an object per request/thread scope.

## 10. How does `isSingleton` relate to caching?

Simplified model:

~~~text
getBean("productName")
        |
        v
Container looks up FactoryBean instance
        |
        +--> What scope does the FactoryBean bean definition have?
        |       |
        |       +-- singleton: can keep one factory instance
        |       '-- prototype: can create a new factory instance
        |
        v
Container checks product metadata
        |
        +-- isSingleton() = true and factory eligible for caching
        |       |
        |       +-- product cache exists -> reuse cached product
        |       '-- not yet cached -> call getObject(), process/potentially cache
        |
        '-- isSingleton() = false
                |
                '-- call getObject() to retrieve product per factory
~~~

The diagram illustrates a **mental model**, not a one-to-one copy of internal implementation. Actual caching has conditions based on bean factory and bean definition; lifecycle/proxies/type-checks may add steps.

Things to remember:

1. Product caching is decided primarily based on the singleton metadata **of the product** and the state of the factory bean in the container.
2. The FactoryBean bean definition still has its own scope.
3. `getObject()` should fulfill its contract accurately rather than staking all correctness on the assumption that caching always preserves everything.
4. `getObjectType()` should describe the product type without forcing product creation just to determine the type.

### Wrong: declaring true yet always creating anew

~~~java
@Override
public Product getObject() {
    return new Product("new");
}

@Override
public boolean isSingleton() {
    return true;
}
~~~

This is an anti-pattern if the contract expects "each direct `getObject()` is new": the factory **tells Spring that the product is a stable reference**, while the implementation returns a new object. Depending on the container/cache, calling `context.getBean` may mask the inconsistency; calling `factory.getObject()` directly will reveal changing references.

Fix in one of two directions:

- **Actually want a singleton:** store and return the same product reference.
- **Actually want a non-singleton:** return `false`; for independent products, implement `getObject()` to create a new object and consider `SmartFactoryBean.isPrototype()` when needed.

## 11. Singleton FactoryBean does not mean a thread-safe product

If `isSingleton() == true`, multiple places may share the same product object.

~~~java
public final class CounterClient {
    private int total;

    public void increment() {
        total++;
    }

    public int getTotal() {
        return total;
    }
}
~~~

This is an illustrative Java class. If `CounterClient` is exposed by a FactoryBean as a singleton product to multiple threads, `total++` **is not an atomic operation**; race conditions can occur.

Remediation must follow the business contract: design the product as immutable, use synchronization/atomics, or move mutable request state to a new object per task. `isSingleton() == true` is only a declaration about **identity/sharing**, and does not provide thread safety.

Conversely, `isSingleton() == false` does not automatically make a product thread-safe if the factory still returns a shared mutable object within another scope.

## 12. Injecting a product into a singleton: why is a non-singleton still retained long-term?

Suppose a singleton service injects a product created by `FreshProductFactory`:

~~~java
@Service
public class JobService {
    private final Product product;

    public JobService(@Qualifier("freshProduct") Product product) {
        this.product = product;
    }

    public String name() {
        return product.value();
    }
}
~~~

This snippet is an illustrative class needing imports for `Service`, `Qualifier`, and the `Product` type.

Even when `FreshProductFactory.isSingleton() == false`, constructor injection of a singleton still happens **when JobService is created**. One product is resolved and stored in the field. Calling `name()` 100 times simply reads back that same reference.

This is analogous to a prototype injected into a singleton: **scope/FactoryBean product metadata controls each time the container is asked**, and does not automatically swap a Java field value after every method invocation.

If each job must get a fresh product, inject a qualified provider:

~~~java
@Service
public class JobService {
    private final ObjectProvider<Product> products;

    public JobService(
            @Qualifier("freshProduct") ObjectProvider<Product> products) {
        this.products = products;
    }

    public String runJob() {
        Product product = products.getObject();
        return product.value();
    }
}
~~~

This is an **alternative version of the class**, needing imports for `ObjectProvider`, `Service`, and `Qualifier`. With the configuration from the runnable example, each `runJob()` requests a fresh product. If the product owns resources, the caller must clean them up according to the job's own lifetime.

## 13. Eager/lazy product is not the same question as singleton

There are three independent questions:

1. **Which object?** — what product does `getObject()` return?
2. **Is it shared?** — `isSingleton()` indicates the shared product contract.
3. **When is it created?** — container/factory decides eager or lazy creation, potentially involving `SmartFactoryBean.isEagerInit()`.

Normally, a singleton FactoryBean is created alongside non-lazy singleton beans, yet **the `getObject()` product is not required to be created eagerly** just because `isSingleton() == true`. A `SmartFactoryBean` can express a desire for eager initialization via `isEagerInit()`.

Do not equate:

- `isSingleton() == true` with "the product is guaranteed to be created by the time context refresh finishes".
- `@Lazy` with "the product will never be shared".
- `isEagerInit() == true` with "every `getObject()` call must create anew".

Those belong to **two different lifecycle axes**: creation timing and degree of sharing.

## 14. How does `getObjectType()` affect autowiring and bean lookup?

When Spring searches for beans of type `Product`, it needs to know which FactoryBeans are capable of exposing `Product`. `getObjectType()` is a key source of metadata.

~~~java
@Override
public Class<?> getObjectType() {
    return Product.class;
}
~~~

**Return a sufficiently accurate type whenever possible**, without creating the product just to find the type. The method may be called before the factory finishes initialization, so do not unsafely rely on state only available after init callbacks.

If `getObjectType()` returns `null` when the type could be known, type-based autowiring or `getBeansOfType` may fail to find the corresponding factory product. Yet calling `getObject()` from `getObjectType()` to "probe the type" can trigger unexpected I/O or side effects.

A good implementation:

~~~java
public final class HttpClientFactory implements FactoryBean<HttpClient> {
    @Override
    public Class<?> getObjectType() {
        return HttpClient.class;
    }
    // getObject() and isSingleton() implemented separately.
}
~~~

This is an incomplete illustrative class skeleton; it requires defining `HttpClient`, importing `FactoryBean`, and implementing `getObject()`.

## 15. Things to note about product lifecycle

A `FactoryBean` is a Spring-managed bean. The product exposed by `getObject()` passes through Spring's own handling mechanism; **do not assume all init/destroy callbacks of the product behave identically to an independent bean definition created directly by Spring**.

For example, a factory might open a network connection and build a proxy client. If the product is a singleton holding a connection/pool:

- Determine whether the resource is owned by the **factory** or the **product**.
- If the factory is responsible, place cleanup in the factory bean's lifecycle (and ensure the factory is managed by Spring).
- If the product implements `AutoCloseable`, consider who calls `close()` and when.
- Do not expect `isSingleton() == true` alone to automatically invoke every destruction callback on an object returned from `getObject()`.
- If the product is non-singleton or prototype-style, the recipient of each product must clearly define cleanup per unit of work.

**`isSingleton()` is not a lifecycle destroy configuration.** It does not replace `@PreDestroy`, `DisposableBean.destroy()`, `@Bean(destroyMethod = "...")`, or `AutoCloseable` ownership.

For objects containing only plain Java data, no special destroy callback is needed. For sockets/file handles/clients needing closing, closing responsibility must be designed independently of Spring's identity caching.

## 16. FactoryBean and `@Bean`: a very easily misunderstood pattern

The snippet:

~~~java
@Configuration
class Config {
    @Bean
    public Product product() {
        return new Product("x");
    }
}
~~~

means the Spring bean definition is an **ordinary Product**. The `product()` method is a **Java factory method of the configuration**, and the returned object does not implement `FactoryBean`. The default scope of the product bean is singleton, determined by the `@Bean` bean definition.

Meanwhile:

~~~java
@Configuration
class Config {
    @Bean
    public FactoryBean<Product> product() {
        return new SharedProductFactory();
    }
}
~~~

Spring registers a **FactoryBean** under the name `product`. Normal lookup by name `product` exposes a `Product`; lookup `&product` exposes the factory. These are two **alternative** configurations—do not put both with the same class/method name in one file. The code requires definitions for `Product`, `SharedProductFactory`, and corresponding imports.

Only in the second case does `FactoryBean.isSingleton()` apply to the product. Do not refer to FactoryBean's `isSingleton()` method in the first example because there is no FactoryBean instance.

## 17. When should you use `FactoryBean` instead of an ordinary `@Bean`?

`FactoryBean` is usually appropriate for **framework/infrastructure integration**:

- The product is created by a process not as simple as calling a constructor.
- You need to expose a proxy from a complex factory.
- You need `getObjectType()` metadata and separate singleton/prototype/eager semantics for the product.
- You want to keep the factory as an infrastructure bean while users inject the product like a normal bean.

If you only need to create a singleton client:

~~~java
@Bean(destroyMethod = "close")
public MyClient myClient(ClientOptions options) {
    return new MyClient(options);
}
~~~

then a direct `@Bean` is usually enough. There is no need to write a `FactoryBean<MyClient>` just to call a constructor or configure a few properties. This illustrative snippet requires definitions for `MyClient`, `ClientOptions`, and the `close()` method.

If you only need a plain Java prototype:

~~~java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public WorkState workState() {
    return new WorkState();
}
~~~

this can also be simpler than writing a custom FactoryBean. This illustrative snippet requires the corresponding imports/types.

## 18. Pitfall cases

| Symptom | Common cause | What to check |
| --- | --- | --- |
| `getObject()` has `new` yet lookups always return the same object | `isSingleton()` defaults to true; product is cached | Override false if non-singleton is genuinely needed |
| `getBean("name")` returns Product instead of FactoryBean | This is the `FactoryBean` contract | Use `getBean("&name")` to get the factory |
| `context.isSingleton("&name")` is true, `factory.isSingleton()` is false | The former queries the factory; the latter queries the product | Distinguish the two axes |
| Two `getBean("name")` calls create a new factory even though product `isSingleton` is true | The factory bean definition may be prototype | Check the factory scope |
| `isSingleton() == false` yet two lookups return the same reference | The factory returns objects from a shared/custom scope | Read `getObject()`, use `SmartFactoryBean.isPrototype()` if independent instances are required |
| `isPrototype("name")` behaves unexpectedly | `SmartFactoryBean` metadata or a scope other than prototype | Read Javadoc and actual factory behavior |
| Product is not autowired by type | `getObjectType()` is wrong or returns null | Return a reliable type, avoiding side effects |
| Singleton product has race conditions | Multiple threads share the same mutable instance | Design immutable/thread-safe, or use an object per operation |
| Singleton service holds onto one non-singleton product forever | Constructor injection resolves once | Use `ObjectProvider<Product>` where appropriate |
| Product is not seen created at startup | Product may be lazy despite singleton factory | Check `SmartFactoryBean.isEagerInit()` and lookup sites |
| Resources are not closed | Confusing caching with lifecycle destroy | Clarify ownership and cleanup |
| Factory proxy has wrong `isSingleton` configuration | Declaration does not match actual returned reference | Align contract with `getObject()` |

### Diagnostic checklist

1. Does the bean under that name actually implement `FactoryBean`?
2. What objects are `getBean("name")` and `getBean("&name")` returning?
3. Is the factory bean definition singleton or prototype?
4. Is `FactoryBean.isSingleton()` returning true/false appropriately for the product?
5. Does `getObject()` create anew, return a cached field, or look up in another scope?
6. Does `getObjectType()` reflect the true type of the product?
7. Is `SmartFactoryBean` involved with `isPrototype()` / `isEagerInit()`?
8. Is a singleton consumer holding a non-singleton product in a field?
9. Does the product have mutable state or resources needing cleanup?
10. Do tests verify identity with `==` and check the number of `getObject()` calls?

## 19. Which unit tests and integration tests are valuable?

### 19.1. Directly testing the factory contract

For `SharedProductFactory` in section 7:

~~~java
var factory = new FactoryBeanProductDemo.SharedProductFactory();
var a = factory.getObject();
var b = factory.getObject();

if (!factory.isSingleton() || a != b) {
    throw new AssertionError("Shared FactoryBean contract violated");
}
~~~

For `FreshProductFactory`:

~~~java
var factory = new FactoryBeanProductDemo.FreshProductFactory();
var a = factory.getObject();
var b = factory.getObject();

if (factory.isSingleton() || a == b) {
    throw new AssertionError("Fresh FactoryBean contract violated");
}
~~~

These are snippets that can be placed in a Java test/main with source from section 7. They verify that the **`getObject()` implementation** is consistent with the declared metadata, without testing Spring caching.

### 19.2. Integration tests must use a real Spring context

A more valuable test of Spring behavior:

~~~java
try (var ctx = new AnnotationConfigApplicationContext(
        FactoryBeanProductDemo.Config.class)) {

    Object shared1 = ctx.getBean("sharedProduct");
    Object shared2 = ctx.getBean("sharedProduct");

    Object fresh1 = ctx.getBean("freshProduct");
    Object fresh2 = ctx.getBean("freshProduct");

    if (shared1 != shared2 || fresh1 == fresh2) {
        throw new AssertionError("Product lookup semantics wrong");
    }

    if (!ctx.isSingleton("&freshProduct")
            || ctx.isSingleton("freshProduct")) {
        throw new AssertionError("Factory/product metadata wrong");
    }
}
~~~

This snippet requires importing `AnnotationConfigApplicationContext` and the section 7 example classes. JUnit is not required to test it, though in production projects you should use JUnit assertions and an integration test context.

Do not test only with `equals()` if the goal is **the same object reference**. Two objects with equal data can still return true from `equals()`. Use `==` to test identity or a valid unique-instance verification mechanism.

### 19.3. Concurrent testing when the factory has a lazy singleton

If the factory lazily creates its product inside `getObject()`, verify whether concurrent calls from multiple threads create multiple products or publish incomplete state. Tests can use a barrier/latch to trigger simultaneous requests and verify identity, without relying on random timing tests as sole proof. Thread-safe factory design is the ultimate guarantee.

## 20. Self-check questions

**Question 1.** Does `FactoryBean.isSingleton()` returning `true` mean the FactoryBean itself is definitely a singleton?

**Answer:** No. It describes the **product** object exposed by `getObject()`. The factory's own bean definition has a separate scope.

**Question 2.** A singleton FactoryBean has `isSingleton() == false`, and each `getObject()` returns `new Product()`. What happens on two ordinary `getBean("name")` calls?

**Answer:** Two different product instances, because the container does not cache them as singleton products and the factory actually creates anew each time. The same factory instance can be reused.

**Question 3.** If you do not override `FactoryBean.isSingleton()` in Spring 6.1, what is the default?

**Answer:** `true`. If you want a non-singleton product, you must declare the metadata properly and ensure matching `getObject()` behavior.

**Question 4.** Why is `isSingleton() == false` insufficient to assert that a product is prototype?

**Answer:** A non-singleton could be an object belonging to a custom/request scope or shared along another boundary, not necessarily independent on every lookup. `SmartFactoryBean.isPrototype()` explicitly expresses independent-instance semantics.

**Question 5.** What is `getBean("&myFactory")` used for?

**Answer:** Retrieving the **FactoryBean object** instead of the product created by `getObject()`. The `&` sign is Spring's dereference prefix.

**Question 6.** Does a prototype FactoryBean returning `isSingleton() == true` create a JVM-wide singleton product?

**Answer:** Not guaranteed. Each factory retrieval under prototype scope can create a new factory instance; the singleton product declaration only belongs to the corresponding factory instance's contract.

**Question 7.** A singleton service injects a fresh product from a non-singleton FactoryBean via constructor. Does every call to the service get a new product?

**Answer:** No. Constructor injection resolves one dependency when the service is created; the field retains that reference. Use `ObjectProvider`/per-operation lookup if the business logic needs a fresh one.

**Question 8.** Should `getObjectType()` call `getObject()` to find the type?

**Answer:** Generally no. Type metadata should be supplied reliably without creating the product or causing side effects prior to actual lookup time.

**Question 9.** Does `isSingleton() == true` make the product thread-safe and automatically destroy resources?

**Answer:** No. It only describes whether the product is shared/cacheable. Concurrency safety and cleanup must be designed separately.

## 21. Practical summary

When reading a `FactoryBean<T>`, ask in the exact order:

1. **With what scope is Spring managing the factory?**
2. **How does `getObject()` actually return references?**
3. **Does `isSingleton()` match that behavior?**
4. **If it returns false, is the product genuinely an independent prototype or following another scope?**
5. **Does the caller retrieve the product with `name` or the factory with `&name`?**
6. **Does the product have state/resources needing protection or cleanup?**

Easy rule to remember:

> **`FactoryBean.isSingleton()` is about the product, not about the factory itself. `true` means shareable/cacheable; `false` means no shared singleton is advertised, though it does not by itself guarantee an independent prototype on every call.**

For ordinary business applications, if you only need to create a simple singleton or prototype, `@Bean` combined with `@Scope` can be more direct and readable. Only use `FactoryBean` when you have a container-integration-level need to create/expose a product.

## 22. Official references

- [Spring Framework Reference — Container Extension Points: FactoryBean](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html): `getObject()`, `getObjectType()`, `isSingleton()`, and `&name` lookup.
- [FactoryBean Javadoc — Spring Framework 6.1.12](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/beans/factory/FactoryBean.html): core contract, default `isSingleton() == true`, warning that `false` does not equate to independent instances.
- [SmartFactoryBean Javadoc — Spring Framework 6.1](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/SmartFactoryBean.html): `isPrototype()` and `isEagerInit()`.
- [BeanFactory Javadoc — Spring Framework 6.1](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/beans/factory/BeanFactory.html): `isSingleton(name)`, `isPrototype(name)`, `getBean(name)`, and factory dereferencing.
- [Spring Framework Reference — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): singleton/prototype and when the container supplies dependencies.
