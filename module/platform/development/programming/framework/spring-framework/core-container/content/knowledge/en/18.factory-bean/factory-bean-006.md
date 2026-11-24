# FactoryBean Lifecycle and Product Management Responsibility in the Spring Core Container

## 1. The problem and key message

`FactoryBean<T>` is a Spring IoC Container extension mechanism enabling **a bean acting as a factory** to create or supply another object. When a bean name is registered for a `FactoryBean`, an ordinary call `context.getBean("name")` returns the **product** from `getObject()`; to retrieve **the factory itself**, use the `&` prefix: `context.getBean("&name")`.

The easiest thing to get wrong is not the `getObject()` syntax, but **two different lifecycles**:

1. **Lifecycle of the FactoryBean instance:** the factory itself is a Spring-managed bean. Spring creates it, injects dependencies, invokes initialization callbacks, applies bean post-processing, and invokes appropriate destroy callbacks when the factory's scope ends.
2. **Lifecycle of the object produced by the FactoryBean:** the container can retrieve the product, cache it according to `isSingleton()`, and apply certain post-processing steps, but **does not automatically manage the product's full initialization/destruction lifecycle like an independent bean definition**. In particular, destroy callbacks, `Closeable.close()`, or `AutoCloseable.close()` on the product **are not automatically invoked by the container simply because the product was returned by a FactoryBean**.

Under the official `FactoryBean` contract, **the FactoryBean is responsible for managing the resources of objects it creates** when the factory truly owns that object. A factory managing a long-lived shared product can implement `DisposableBean` and forward `destroy()` to `product.close()`. If the factory creates many unshared products, code using the product or a dedicated owner must provide a cleanup mechanism for each instance.

~~~text
Bean definition: "connectionClient" → ConnectionClientFactoryBean
                             │
Spring creates & manages     ▼
              FactoryBean instance
              - constructor
              - dependency injection
              - @PostConstruct / InitializingBean
              - destroy callback per factory scope
                             │
                       getObject()
                             ▼
                      Product object
              - can be shared/cached
              - can be created anew per lookup
              - NOT automatically invoked by Spring for
                @PreDestroy/DisposableBean/close like an ordinary bean
                             │
                        Who closes?
              FactoryBean or each product's owner
~~~

**Knowledge warning:** `FactoryBean` is completely different from the concept of *a factory method* annotated with `@Bean` and different from **BeanFactory**. They can be combined, yet they are not the same API.

## 2. The `FactoryBean<T>` contract

The interface resides in package `org.springframework.beans.factory`. Abbreviated form:

~~~java
public interface FactoryBean<T> {
    T getObject() throws Exception;
    Class<?> getObjectType();
    default boolean isSingleton() {
        return true;
    }
}
~~~

In real code, `getObject()` and `getObjectType()` may return `null` under the API contract (with corresponding conditions and consequences); Spring has special handling for those cases.

### 2.1. `getObject()`

Returns the product. The product may:

- Be constructed anew with a constructor/SDK builder.
- Be retrieved from a library or resource manager.
- Be an infrastructure proxy.
- Be an object cached internally by the factory for reuse.
- Be a resource holding a socket, file handle, thread, or connection pool, thus requiring clear ownership/cleanup.

You should not assume `getObject()` always runs on every call to `context.getBean(...)`, because Spring may cache a singleton product. Nor should you call `factory.getObject()` directly and infer `BeanFactory` caching behavior: a direct call bypasses the container's product-handling pipeline, unless the factory caches internally.

### 2.2. `getObjectType()`

Returns the product's type, helping the container perform type-based lookups/autowiring without necessarily creating the product. For example, the factory returns `Client.class` if `getObject()` returns `Client`.

Important contract:

- Should return a meaningful type **early and consistently**, even before the factory is fully initialized.
- Do not create heavy resources, open network connections, or rely on state only available after `@PostConstruct` runs.
- May return `null` if the type is undetermined, though by-type autowiring may then **skip** the factory, causing confusing errors.
- `getObjectType()` may be called multiple times at different bootstrap points; do not use it as an init method.

### 2.3. `isSingleton()`

Governs the **semantics of the product**, not the scope of the FactoryBean itself.

- `true`: the factory promises the product is a shareable reference, and the container may cache the product of a singleton FactoryBean. This is the **default** on the modern interface.
- `false`: the product is not treated as a shared singleton under the factory's contract; BeanFactory normally calls the factory to obtain a product for the next lookup. This **does not necessarily guarantee each product has a distinct identity**; the factory may reuse objects on its own for separate reasons.

Only return `true` when a stable product reference can be guaranteed. If `getObject()` always `new`s a different object while `isSingleton()` reports `true`, Spring may cache the first product, causing semantics to diverge between calling through the container and calling the factory directly.

### 2.4. `SmartFactoryBean<T>`

`SmartFactoryBean` adds information such as `isPrototype()` (defining an independent product in the prototype sense) and `isEagerInit()` (requesting product initialization during the eager singleton initialization phase when appropriate). This is an **advanced** contract, unnecessary for every custom FactoryBean.

`FactoryBean.isSingleton() == false` and `SmartFactoryBean.isPrototype() == true` are not completely the same concept. `isSingleton=false` only states the product is not a shared singleton; whereas `isPrototype=true` confirms the factory actually creates independent instances under the extended contract.

## 3. Distinguishing three easily confused concepts

| Concept | Role | Who supplies the object | When typically used |
| --- | --- | --- | --- |
| `BeanFactory` | Container API creating and managing beans | Spring BeanFactory itself | DI container, metadata, bean lookup |
| `FactoryBean<T>` | Special Spring bean producing another object | `getObject()` code in custom factory | Complex object setup, proxy/SDK integration |
| `@Bean` method | Bean definition based on a factory method | Method in `@Configuration`/component | Standard Java config bean registration |
| Plain Java factory | Class/method creating objects in Java | Java application code | When Spring-specific FactoryBean semantics are unnecessary |

The following two snippets are not equivalent in lifecycle:

~~~java
// Ordinary bean: the product is a bean directly managed by Spring.
@Bean(destroyMethod = "close")
RemoteClient remoteClient() {
    return new RemoteClient();
}
~~~

~~~java
// FactoryBean: bean definition returns a special factory.
// Normal lookup of the bean name returns the product from getObject().
@Bean
FactoryBean<RemoteClient> remoteClient() {
    return new RemoteClientFactoryBean();
}
~~~

Both snippets are illustrative examples, assuming `RemoteClient`/`RemoteClientFactoryBean` classes and required imports exist. In the first snippet, `RemoteClient` is a direct bean: `destroyMethod="close"` attaches to that bean definition itself. In the second snippet, the bean definition's lifecycle primarily applies to the **FactoryBean instance**; the `RemoteClient` product does not automatically receive the same destroy callback.

If the product needs a full chain of Spring lifecycle callbacks, consider registering it as a **regular bean** rather than having a FactoryBean create and return it.

## 4. How is a FactoryBean created and initialized?

When the container needs a FactoryBean instance, Spring executes the normal Spring-managed bean process:

1. Read the bean definition, determining the class or `@Bean` factory method that creates the FactoryBean.
2. Resolve constructor/factory method arguments and instantiate the FactoryBean.
3. Inject dependencies via constructor, setter, `@Autowired`, or other supported mechanisms.
4. Invoke Aware callbacks if the factory implements them (such as `BeanNameAware`, `BeanFactoryAware`, `ApplicationContextAware` when context applies).
5. Run `BeanPostProcessor`s and initialization callbacks of the **FactoryBean**: `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, and configured custom `initMethod`.
6. The factory bean instance is managed in the scope specified by the factory's bean definition.
7. When the product is needed, the container invokes `FactoryBean.getObject()` (or uses the product cache). When the factory itself needs closing, Spring runs the destroy callback appropriate for the factory's scope.

A `singleton`-scoped FactoryBean is the common configuration. Some custom factories may lazy-init, and some `SmartFactoryBean` implementations have an eager product initialization policy; therefore **do not guess** that `getObject()` always runs right after `afterPropertiesSet()` or only runs when application code calls `getBean()`. You must understand the bean graph and eager/lazy policies.

### Difference between factory and product on a timeline

~~~text
t0 Spring registers bean definition "managedClient"
t1 Creates and injects ManagedClientFactoryBean
t2 FactoryBean.@PostConstruct / afterPropertiesSet()
t3 FactoryBean completes Spring post-processing
t4 Client product is needed → FactoryBean.getObject()
t5 BeanFactory may post-process/cache the product
t6 Application code receives and uses the product
t7 Context shutdown → FactoryBean destroy callback
t8 FactoryBean forwards close to the product if the factory owns it
~~~

This is an **illustrative timeline**; `getObjectType()` may be called before t2 and multiple times. If the factory is prototype-scoped or if the lookup mechanism differs, repeated factory/product creation may vary. Do not write logic that depends on the exact call count of `getObjectType()` or the exact moment of first caching.

## 5. Getting the factory or getting the product: `name` and `&name`

Suppose the configuration has bean name `managedClient`, with a bean definition pointing to `ManagedClientFactoryBean implements FactoryBean<Client>`.

~~~java
// Client is the product.
Client client = context.getBean("managedClient", Client.class);

// FactoryBean is the object that creates the product:
ManagedClientFactoryBean factory =
        context.getBean("&managedClient", ManagedClientFactoryBean.class);
~~~

This is a snippet assuming `context` and corresponding types exist.

Rules:

- `getBean("managedClient")` → object from `getObject()`, potentially a cached product.
- `getBean("&managedClient")` → the FactoryBean instance.
- `getBean(Client.class)` → can resolve the FactoryBean's product if `getObjectType()` declares a matching type, unambiguous with other beans.
- `getBean(ManagedClientFactoryBean.class)` → depends on type lookup and bean definitions, though when you unambiguously want the factory, `&beanName` is the clearest syntax.

The `&` character here is Spring's **factory dereference prefix**, not an AND sign or special Java syntax. Aliased bean names still must resolve via the container's naming mechanism.

Common error: casting `context.getBean("managedClient")` to `ManagedClientFactoryBean` receives the product and typically throws `ClassCastException`. Use `&managedClient` if the goal is configuring/debugging the factory.

## 6. Two independent scopes: FactoryBean scope and product sharing policy

Must distinguish:

- **Scope of the FactoryBean instance** managed by the bean definition, e.g., singleton or prototype.
- **Product sharing semantics** described by `FactoryBean.isSingleton()` and (if present) `SmartFactoryBean.isPrototype()`.

| FactoryBean scope | Product `isSingleton()` | Typical behavior | Lifecycle consequence |
| --- | --- | --- | --- |
| Singleton | `true` | One factory instance, shared/cached product | Singleton factory can clean up product on destroy |
| Singleton | `false` | One factory instance, multiple `getObject()` calls on demand | Factory must track products if it takes ownership; or caller closes them |
| Prototype | `true` | Each factory lookup may yield a separate factory instance; singleton guarantee applies per single factory | Do not expect container-wide caching of one fixed singleton factory |
| Prototype | `false` | Factory may be re-created, and product may also be new | Spring does not automatically destroy each issued prototype factory |
| Singleton + `SmartFactoryBean` | Depends on config | Adds independent/eager product information | Must inspect the extended contract |

The table depicts common patterns, not every combination of APIs/proxies/custom scopes. **Never interpret `isSingleton()` as `@Scope("singleton")` of the FactoryBean.**

### If the product needs per-use state

When a factory returns independent products, each caller must establish when a product is created, across how many method calls it is used, and who owns closing it. For example, suppose the product is a mutable processing session:

~~~java
ProcessingSession session = context.getBean(
        "processingSession", ProcessingSession.class);
try {
    session.process(batch);
    session.commit();
} finally {
    session.close();
}
~~~

This snippet illustrates the ownership idea. `ProcessingSession` needs a contract-compliant `close()`, and the factory must be configured to return independent products if business logic requires it. Do not allow a non-thread-safe product to be shared merely because `isSingleton()` was accidentally left at its default `true`.

## 7. Does the container process the product at all?

Yes, though it must be stated accurately.

### 7.1. The product lacks a full ordinary bean lifecycle

Spring manages the FactoryBean instance. The factory's `getObject()` creates the product; Spring may apply `BeanPostProcessor.postProcessAfterInitialization(...)` to the product, for example to create a proxy. However, there is **no complete pipeline** of constructor injection, property population, Aware callbacks, `@PostConstruct`, `InitializingBean`, and destroy callbacks for the product simply because it was returned by a FactoryBean.

Thus saying "the product is completely invisible to Spring" is **inaccurate** (since BeanFactory knows about it, can cache it, and can post-process it), while saying "the product is managed by Spring identically to an ordinary bean" is **also wrong**.

### 7.2. What if the product needs dependencies?

The factory can receive constructor-injected dependencies and **pass them** to the product:

~~~java
public final class ClientFactoryBean implements FactoryBean<Client> {
    private final HttpTransport transport;

    public ClientFactoryBean(HttpTransport transport) {
        this.transport = transport;
    }

    @Override
    public Client getObject() {
        return new Client(transport);
    }

    @Override
    public Class<?> getObjectType() {
        return Client.class;
    }
}
~~~

This is an illustrative snippet requiring `HttpTransport` and `Client` definitions. Spring DI applies to the **factory**, and does not automatically scan `@Autowired` fields inside a `Client` freshly created with `new`.

If you need Spring wiring on a manually created object, BeanFactory has specialized autowiring/initialization APIs; however, invoking them requires understanding lifecycle and cleanup, without assuming they turn the object into a full managed bean with automatic destruction. Most application code should **prefer `@Bean` returning the product directly** unless there is a reason to use FactoryBean.

### 7.3. BeanPostProcessor does not equate to a destroy callback

A custom BeanPostProcessor or auto-proxy creator may act upon the product; that is **post-processing after the factory has supplied the object**, and does not mean Spring will automatically call `@PreDestroy` or `DisposableBean.destroy()` on the product when the context closes. The two mechanisms are separate.

## 8. Who owns the product and who must release resources?

Ownership is a design decision, not merely a `FactoryBean` flag.

### Case A — The factory owns a single shared product

For example, a FactoryBean managing an SDK client with a connection pool, with one instance used throughout the singleton factory's lifetime. The factory can implement `DisposableBean`:

~~~java
public final class SdkClientFactoryBean
        implements FactoryBean<SdkClient>, DisposableBean {

    private SdkClient client;

    @Override
    public synchronized SdkClient getObject() {
        if (client == null) {
            client = new SdkClient();
        }
        return client;
    }

    @Override
    public Class<?> getObjectType() {
        return SdkClient.class;
    }

    @Override
    public boolean isSingleton() {
        return true;
    }

    @Override
    public synchronized void destroy() {
        if (client != null) {
            client.close();
        }
    }
}
~~~

This is an **illustrative pattern**, requiring `SdkClient` implementing `close()`, and imports for `FactoryBean` and `DisposableBean`. When the factory is a singleton Spring-managed bean, Spring calls the factory's `destroy()` during proper context shutdown. The factory checks whether `client` has been created to avoid opening a client just to close it.

### Case B — Multiple independent products

If `getObject()` always creates a new object and `isSingleton()` returns `false`, the factory must **choose an explicit ownership policy**:

- **Caller owns:** the caller obtains the product and closes it with `try-with-resources`/`finally` after the operation. The factory does not try to close objects it has handed over if ownership is transferred.
- **Factory owns:** the factory keeps a controlled registry of live products and closes them at factory shutdown or via lease/reference-counting. Concurrency, memory, and one `close` error affecting others must be designed carefully.
- **An external resource manager owns:** the product may just be a handle/borrowed view; only the resource manager is allowed to close it. The factory must communicate ownership via API/documentation.

There is no "default Spring finalizer" that automatically tracks and closes every object `getObject()` ever returned. In particular, non-singleton products may be used after the factory no longer knows who holds references; hence transferring closing rights to the caller is often the clearest approach.

### Case C — The factory is prototype

Even if the factory implements `DisposableBean`, Spring **does not by default destroy every prototype instance** after handing it to callers. Therefore `DisposableBean.destroy()` on a prototype factory is not automatically guaranteed on context close; separate ownership design is still required.

### Case D — The product holds no resources

A value object with no `close`, thread, or unmanaged resource may need no special cleanup mechanism. Do not add `DisposableBean` just to look "complete" if nothing actually needs releasing.

## 9. Complete Java 17 example: factory manages shared client, caller manages non-shared client

This example runs with **Java 17**, **Maven**, and **Spring Framework 6.2.12**, without Spring Boot or an HTTP server. The program demonstrates:

1. Spring invokes the FactoryBean's `InitializingBean.afterPropertiesSet()`.
2. The `&` prefix retrieves the FactoryBean itself.
3. The `isSingleton()==true` product is reused.
4. `isSingleton()==false` supplies two independent products in the example.
5. The caller closes the two non-shared products itself.
6. Upon closing the context, Spring invokes `DisposableBean.destroy()` on the singleton factory; the factory forwards `close()` to the shared product.

File structure:

~~~text
factorybean-lifecycle/
├── pom.xml
└── src/main/java/example/FactoryBeanLifecycleDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>factorybean-lifecycle</artifactId>
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

`src/main/java/example/FactoryBeanLifecycleDemo.java`:

~~~java
package example;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.FactoryBean;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class FactoryBeanLifecycleDemo {

    public static void main(String[] args) {
        Client shared;
        OwnedClientFactoryBean owner;

        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            owner = context.getBean("&ownedClient",
                    OwnedClientFactoryBean.class);
            System.out.println("Factory initialized: " + owner.initialized());

            shared = context.getBean("ownedClient", Client.class);
            Client sharedAgain = context.getBean("ownedClient", Client.class);
            System.out.println("Shared product reused: "
                    + (shared == sharedAgain));

            Client first = context.getBean("freshClient", Client.class);
            Client second = context.getBean("freshClient", Client.class);
            System.out.println("Non-shared products different: "
                    + (first != second));

            System.out.println("Non-shared before close: "
                    + (first.isClosed() || second.isClosed()));

            first.close();
            second.close();
            System.out.println("Non-shared manually closed: "
                    + (first.isClosed() && second.isClosed()));

            System.out.println("Shared before shutdown: "
                    + shared.isClosed());
        }

        System.out.println("Factory destroyed: " + owner.destroyed());
        System.out.println("Shared after shutdown: " + shared.isClosed());
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean("ownedClient")
        public OwnedClientFactoryBean ownedClientFactory() {
            return new OwnedClientFactoryBean();
        }

        @Bean("freshClient")
        public FreshClientFactoryBean freshClientFactory() {
            return new FreshClientFactoryBean();
        }
    }

    public static final class Client implements AutoCloseable {
        private boolean closed;

        public boolean isClosed() {
            return closed;
        }

        @Override
        public void close() {
            closed = true;
        }
    }

    public static final class OwnedClientFactoryBean
            implements FactoryBean<Client>,
                       InitializingBean, DisposableBean {

        private Client client;
        private boolean initialized;
        private boolean destroyed;

        @Override
        public void afterPropertiesSet() {
            initialized = true;
        }

        @Override
        public synchronized Client getObject() {
            if (!initialized) {
                throw new IllegalStateException("Factory not initialized");
            }
            if (client == null) {
                client = new Client();
            }
            return client;
        }

        @Override
        public Class<?> getObjectType() {
            return Client.class;
        }

        @Override
        public boolean isSingleton() {
            return true;
        }

        public boolean initialized() {
            return initialized;
        }

        public boolean destroyed() {
            return destroyed;
        }

        @Override
        public synchronized void destroy() {
            destroyed = true;
            if (client != null) {
                client.close();
            }
        }
    }

    public static final class FreshClientFactoryBean
            implements FactoryBean<Client> {

        @Override
        public Client getObject() {
            return new Client();
        }

        @Override
        public Class<?> getObjectType() {
            return Client.class;
        }

        @Override
        public boolean isSingleton() {
            return false;
        }
    }
}
~~~

Run inside the `factorybean-lifecycle` directory:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.FactoryBeanLifecycleDemo
~~~

Stdout from the `System.out.println` statements in the program (excluding Maven or environment-specific logging):

~~~text
Factory initialized: true
Shared product reused: true
Non-shared products different: true
Non-shared before close: false
Non-shared manually closed: true
Shared before shutdown: false
Factory destroyed: true
Shared after shutdown: true
~~~

**Why is the stdout deterministic?**

- Both FactoryBeans registered via `@Bean` are singletons and are initialized by the container during the refresh phase. `OwnedClientFactoryBean.afterPropertiesSet()` sets `initialized=true`; the program retrieves the factory via `&ownedClient` after refresh.
- Calling `getBean("ownedClient")` routes the product through the FactoryBean mechanism. `OwnedClientFactoryBean` caches `Client` in a field and reports `isSingleton()==true`, so the two lookups in the example receive the same reference.
- `FreshClientFactoryBean.isSingleton()==false` and `getObject()` returns `new Client()` on each call. The two `freshClient` lookups therefore receive two different objects. This is a property of **this specific implementation**, not an absolute definition for every FactoryBean returning false.
- Nothing automatically closes the two fresh clients if the caller does not invoke `close()`. The two statements `first.close()` and `second.close()` demonstrate **caller ownership**.
- At the end of `try-with-resources`, `context.close()` is invoked. Spring destroys `OwnedClientFactoryBean` itself; inside `destroy()`, the factory calls `client.close()`. The shared product is closed **indirectly by its owner**, not because the container found a separate `Client` bean definition to invoke a destroy callback on.
- Checking `shared.isClosed()` outside the context still reads the state of the Java object referenced in `main`; do not use the client to connect again after it has been closed.

This program simulates a resource lifecycle with a `closed` flag without creating real sockets or networks. With a real client, `close()` can throw exceptions, requiring decisions on logging, propagation, timeouts, and cleanup of other resources when multiple clients exist.

## 10. What if `@PreDestroy` on the product is needed?

A common mistaken inference:

~~~java
public final class ExternalClient {
    @PreDestroy
    public void cleanup() {
        closeNetworkResources();
    }
}
~~~

If `ExternalClient` is merely instantiated with `new` by `FactoryBean.getObject()` and returned, that annotation **does not by itself guarantee Spring will call cleanup** at context shutdown.

Ways to handle it:

1. **Factory owns:** the FactoryBean is a singleton, implements `DisposableBean` or declares a factory destroy callback, and invokes `product.close()`.
2. **Caller owns:** for short-lived products, the caller uses `try-with-resources`/`finally` to close at the right time.
3. **Register the product as an ordinary bean:** if full Spring DI/init/destroy semantics are needed and `FactoryBean` is not strictly required, use `@Bean(initMethod = "...", destroyMethod = "close")` returning the product directly.
4. **Resource manager owns:** the product is a view/lease; only the manager closes the underlying resource according to the manager's lifecycle.

Do not both require the factory to close the product automatically and let callers freely close a shared product while other users are active. **Double-close**, premature closing, and use-after-close are real-world resource ownership bugs.

### When the factory has never created the product

A singleton factory can be initialized and destroyed by Spring without `getObject()` ever having been called. `destroy()` must safely handle `product==null`, rather than creating a new client just to call `close()`.

### When the product is not singleton

The factory may no longer know all products it has issued. For the factory to manage all of them requires a tracking registry and an eviction/cleanup policy, avoiding holding references forever and causing memory leaks. If tracking is unnecessary, explicitly transfer ownership to the caller.

## 11. FactoryBean and BeanPostProcessor: not simply "unprocessed"

Spring may apply BeanPostProcessors' `postProcessAfterInitialization` to the product returned by `getObject()`, for instance for wrapping/proxying. However, that process **is not the full lifecycle** of a normal bean.

Comparison table:

| Activity | FactoryBean instance | Product returned by `getObject()` |
| --- | --- | --- |
| Spring creates instance from bean definition | Yes | Normally created by the FactoryBean |
| Constructor/factory method DI of the object itself | Yes per bean definition | Handled by FactoryBean's own logic |
| Automatic setter/field autowiring | Yes, if configured properly | Not by default merely from being returned |
| Aware callbacks | Yes, if the factory implements them | Not by default |
| Object's `@PostConstruct`/`InitializingBean` | Yes | Not by default |
| `BeanPostProcessor` after initialization | Yes | Possibly, depending on BeanFactory/mechanism |
| Spring caches shared product | Factory instance per bean scope | May cache per `isSingleton()` |
| `@PreDestroy`/`DisposableBean` on the object | Per factory scope | Not automatic |
| Cleaning up underlying resources | Factory must clean up resources it owns | Factory/caller/resource manager per ownership |

Do not write `@Autowired` fields inside the product and expect Spring to inject them just because the product is a "bean visible through getBean". If a `Transport` dependency is needed inside the product, inject `Transport` into the **FactoryBean** and pass it to the product's constructor; or change the architecture so the product is actually a directly Spring-managed bean.

### Type prediction can happen very early

`getObjectType()` may be called **before the factory is completely initialized**, including during autowiring/by-type lookups. Therefore do not open connections or create the product just to determine the type. For a type known upfront:

~~~java
@Override
public Class<?> getObjectType() {
    return ExternalClient.class;
}
~~~

This is a method snippet. If the type is unknown, `null` is allowed, though Spring may fail to recognize the product during by-type autowiring. Do not "fix" this by forcing every `getObjectType()` call to create the product.

## 12. Thread safety and cache ownership

FactoryBeans are often accessed indirectly by multiple threads via BeanFactory. If the factory caches a singleton product itself, the lazy creation logic needs thread safety.

Example:

~~~java
private Client client;

@Override
public synchronized Client getObject() {
    if (client == null) {
        client = new Client();
    }
    return client;
}
~~~

This is a snippet. `synchronized` ensures the factory does not itself create two objects when two threads call `getObject()` directly. Along the normal access path, Spring also synchronizes singleton creation/caching; however, **you should not rely solely on Spring's cache to protect the factory's own mutable state when code may call the factory directly**.

If the real client has non-thread-safe methods, having the factory return the same singleton **does not make the client thread-safe**. Only cache in the factory when the product is safe to share or is protected via proper pooling/synchronization.

With multiple products needing release, a tracking registry must handle races between `getObject()` and `destroy()`, exceptions during close, and avoid retaining references indefinitely to unshared products already closed by callers. Final responsibility must rest with a single owner or an explicit sharing contract.

## 13. Does putting FactoryBean in prototype scope solve cleanup?

No. Prototype scope on the **factory** causes Spring to be able to create a new FactoryBean instance per lookup, yet Spring does not proactively reclaim and invoke destroy callbacks for every prototype factory after handing them out. That can worsen resource leaks if each prototype factory owns a client.

Two separate concerns:

- **Need a new product per job:** a singleton FactoryBean with `isSingleton=false` and caller ownership may suffice.
- **Need a new factory instance per job:** only then think about a prototype factory, and you must manage both the factory instance and the product yourself.

For the use case "an object that changes on every request", before writing a FactoryBean consider a normal `@Scope("prototype")` bean or `ObjectProvider<T>`. `FactoryBean` makes sense when there is complex SDK/proxy object creation logic, type prediction, integration specifics, or a need to supply products through a single bean definition.

## 14. Common errors and how to fix them

| Symptom | Cause | How to fix |
| --- | --- | --- |
| `getBean("x")` returns product instead of factory | FactoryBean is dereferenced to its product by default | Use `getBean("&x")` if the factory is needed |
| `@PreDestroy` on the product does not run | Spring only manages destruction of the FactoryBean | Have factory `DisposableBean.destroy` call `product.close` or switch to a regular bean |
| Context closes yet resources stay open | Product owner was not defined | Design explicit factory/caller cleanup |
| Singleton factory returns inconsistent products while `isSingleton=true` | Container may cache the first product | Fix `isSingleton=false` or cache the same reference yourself |
| Non-singleton product leaks | Caller forgot to close; factory does not track | `try-with-resources`/`finally` or registry ownership |
| `getObjectType()==null` causes autowiring failure | Spring cannot predict the product type | Return the right class without creating heavy products |
| `getObjectType()` runs while init fields are still null | Type prediction can occur very early | Rely on stable type metadata |
| Product has `@Autowired` fields that stay null | Product is not wired via the full bean lifecycle | Inject into the factory and pass dependencies |
| Product state differs from expectations | Confusing factory scope with product `isSingleton` | Inspect both configuration axes |
| Factory scope is prototype yet destroy does not run | Spring does not automatically destroy prototypes | Caller or owner must release |
| Shared product is closed mid-request | Caller closed a shared product itself | Factory/resource manager retains ownership of shared product |
| Double-close or race on shutdown | Multiple owners, missing synchronization | Single ownership contract and clear shutdown flow |
| Thinking `@Bean` method is the same as FactoryBean | Two mechanisms have different semantics | If full bean lifecycle is wanted, register the product directly |
| Autowiring picks wrong bean of the same type | Multiple products of same type or wrong type metadata | Use name/qualifier/`@Primary` and accurate `getObjectType` |
| Client opens connection inside `getObjectType()` | Type lookup has side effects | Return pure class, open resources in `getObject` |

## 15. How to verify with tests

### 15.1. FactoryBean contract test

A plain Java unit test for the factory can verify:

- `getObjectType()` returns the expected class without creating connections/clients.
- `isSingleton()==true` accompanies `getObject()` returning a stable reference when the factory caches internally.
- `isSingleton()==false` with prototype-like design creates independent objects when needed.
- `destroy()` only closes resources owned by the factory, without trying to close caller-owned resources by mistake.
- `destroy()` is safe if the product was never created.
- Two threads calling `getObject()` do not violate caching/thread safety if the factory supports concurrent use.

### 15.2. Spring integration test

Use `AnnotationConfigApplicationContext` and assert:

~~~java
Object product = context.getBean("managedClient");
Object factory = context.getBean("&managedClient");

if (!(factory instanceof FactoryBean<?>)) {
    throw new AssertionError("Expected FactoryBean");
}
if (product == factory) {
    throw new AssertionError("Expected distinct product and factory");
}
~~~

This is a snippet requiring an initialized `context`, a `FactoryBean` import, and an actual `managedClient` bean definition.

Next, close the context and verify that owner cleanup was invoked. Do not merely assert that `context.close()` throws no errors: underlying resources must also transition to the closed state.

### 15.3. Testing product lifecycle must not be assumed

If the product has `@PostConstruct`/`@PreDestroy`, test in practice whether you process those annotations yourself or registered the product as a regular bean. Simply because `context.getBean("managedClient")` returns `Client` does not mean every lifecycle annotation on `Client` will execute like an independent bean definition.

## 16. Self-check questions

**Question 1.** How do `context.getBean("client")` and `context.getBean("&client")` differ when the bean is a FactoryBean?

**Answer:** The first call retrieves the product supplied by the FactoryBean; the second call retrieves the FactoryBean instance itself.

**Question 2.** A singleton FactoryBean implements `DisposableBean`. Its product implements `AutoCloseable`. When closing the context, does Spring automatically call `product.close()`?

**Answer:** Not merely because the product implements `AutoCloseable`. The container destroys the factory; the factory must forward closing to the product if it is the owner, or another owner must handle it.

**Question 3.** Does `FactoryBean.isSingleton() == true` mean the FactoryBean bean definition is definitely singleton?

**Answer:** No. `isSingleton()` refers to the product; the FactoryBean's scope is managed separately by its bean definition/container.

**Question 4.** Does `isSingleton() == false` guarantee two `getBean("client")` calls return two Java objects with different identities?

**Answer:** Not absolutely. A non-shared contract does not equate to guaranteeing independent product references for every factory implementation. A factory may manage its own cache; `SmartFactoryBean.isPrototype()` communicates additional semantics if used.

**Question 5.** Can `getObjectType()` be called before initialization of the FactoryBean?

**Answer:** Yes. Therefore return the expected type from stable metadata, avoiding reliance on init state or opening resources here.

**Question 6.** Is a product from a FactoryBean ever processed by a BeanPostProcessor?

**Answer:** It may be processed after initialization for wrapping/proxying by BeanFactory. However, do not confuse this step with full autowiring/init/destroy lifecycle like a regular bean.

**Question 7.** A singleton FactoryBean returns a new client on every `getObject()` and forgets to override `isSingleton()`. What is the issue?

**Answer:** `isSingleton()` defaults to true. Spring may cache the first client, making lookups through the container inconsistent with direct `getObject()`. Choose a consistent contract.

**Question 8.** A factory creates multiple unshared clients. Who must close them?

**Answer:** Per the ownership contract: usually the caller after use; or the factory/resource manager if it actively tracks them and assumes cleanup responsibility. You cannot rely on the container automatically calling destroy on each product.

**Question 9.** Should you use FactoryBean for every complex object?

**Answer:** No. If a `@Bean` method returning the product directly is clear enough and you want Spring to manage the full lifecycle, `@Bean` is usually simpler and has fewer pitfalls.

## 17. Production design checklist

1. Confirm whether FactoryBean is genuinely needed instead of `@Bean` or a plain Java factory.
2. Distinguish the factory bean name from product lookup; document `&beanName` when needed for debugging.
3. `getObjectType()` returns the right class, is lightweight, and does not depend on initialization having completed.
4. Choose `isSingleton()` consistently with the product's identity/lifetime.
5. Inspect the scope of the **factory bean definition**, not just the flag about the product.
6. Have a clear intent for caching the product versus creating a new product on each lookup.
7. If the product is a resource, declare a **single owner** and when `close()` occurs.
8. For singleton products, a singleton factory has `DisposableBean`/destroy callback forwarding cleanup if the factory owns it.
9. For non-shared products, callers use `try-with-resources` or the factory has appropriate tracking.
10. If the FactoryBean is prototype, do not rely on Spring's automatic destroy callback for each instance.
11. Do not assume `@Autowired`, `@PostConstruct`, or `@PreDestroy` on the product operate automatically like a regular bean.
12. Check that the product can be post-processed/proxied; do not confuse proxy identity with the raw target.
13. Ensure thread safety if the factory caches the product or directly receives concurrent calls.
14. Test cases where the product was never created, created multiple times, factory destroyed on context close, double-close, and cleanup exceptions.
15. Do not retain a closed product to serve other requests; define lifecycle and readiness clearly.

## 18. Official references

- [Spring Framework — Customizing Instantiation Logic with a FactoryBean](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html#beans-factory-extension-factorybean)
- [Spring Framework — BeanFactory API](https://docs.spring.io/spring-framework/reference/core/beans/beanfactory.html)
- [Spring Framework — Customizing the Nature of a Bean: Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Spring Framework Javadoc — FactoryBean](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/FactoryBean.html)
- [Spring Framework Javadoc — SmartFactoryBean](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/SmartFactoryBean.html)
- [Spring Framework Javadoc — DisposableBean](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/DisposableBean.html)
