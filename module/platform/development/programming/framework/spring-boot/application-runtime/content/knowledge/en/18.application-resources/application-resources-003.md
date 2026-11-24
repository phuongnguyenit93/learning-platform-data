# AutoCloseable and @Bean Destroy Method Inference in Spring Boot

## 1. The Problem: Once a Bean Is Created, Who Releases Its Resources?

In a Spring Boot application, not every object simply holds data and gets cleaned up by the garbage collector. Some objects hold **resources that require intentional closing**, such as connection pools, HTTP clients, message producers, file handles, timers, thread pools, or client SDKs with long-lived sessions.

A Java object may expose a **close()**, **shutdown()**, or **release()** method to free resources. When that object is returned from a **@Bean** method, Spring Framework needs to know whether it should automatically invoke the destroy method when `ApplicationContext` closes.

Hypothetical example:

~~~java
@Bean
RemoteClient remoteClient() {
    return new RemoteClient();
}
~~~

If **RemoteClient** has a **public void close()** method, Spring usually **automatically recognizes** this method when registering a destruction callback for the bean. You **are not required** to write **@Bean(destroyMethod = "close")** in the standard case.

That mechanism is called **destroy method inference**. It is tied to container-managed bean lifecycles, not garbage collector magic or a background leak-detection thread.

Key questions this lesson answers:

1. What roles do **AutoCloseable** and **Closeable** play for Java resources?
2. Why can a **@Bean** without a declared `destroyMethod` still invoke **close()** or **shutdown()**?
3. What is the difference between the **default destroyMethod**, **destroyMethod = "cleanup"**, and **destroyMethod = ""**?
4. When **@PreDestroy**, **DisposableBean**, and an inferred destroy method coexist, what is the order?
5. Does Spring close every instance, every scope, and every resource returned via `@Bean`?
6. When should you **prevent Spring from automatically closing an externally owned resource**?

**Example scope:** Spring Boot 3.5.x, Spring Framework 6.2.x, and Java 17+. This is a **Spring Framework bean lifecycle** mechanism used by Spring Boot when managing `ApplicationContext`.

## 2. What Is AutoCloseable in Java?

The interface is named **java.lang.AutoCloseable**, designed in Java for resources that need closing.

~~~java
public interface AutoCloseable {
    void close() throws Exception;
}
~~~

**AutoCloseable.close()** represents the action of releasing a resource. It allows Java code to use **try-with-resources** to invoke close automatically at the end of a try block, even when an exception occurs.

Standard Java example, independent of Spring:

~~~java
public class PlainAutoCloseDemo {

    static final class Resource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("resource.close()");
        }

        void use() {
            System.out.println("resource.use()");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            resource.use();
        }

        System.out.println("after try");
    }
}
~~~

Save as **PlainAutoCloseDemo.java**, and run:

~~~bash
javac PlainAutoCloseDemo.java
java PlainAutoCloseDemo
~~~

Exact output:

~~~text
resource.use()
resource.close()
after try
~~~

In this example, **the Java compiler and try-with-resources** perform the close call. **There is no Spring ApplicationContext**.

### AutoCloseable and java.io.Closeable

**java.io.Closeable** also provides **close()**, and extends **AutoCloseable**. `Closeable` fits I/O resources and carries a specific `IOException` contract, whereas `AutoCloseable` is more general.

| API | Purpose | Declared Exception Type |
| --- | --- | --- |
| **AutoCloseable** | Any resource needing cleanup | **Exception** |
| **Closeable** | I/O resources and similar | **IOException** |
| **DisposableBean** | Destruction callback tied directly to Spring | **Exception** |
| **@PreDestroy** | Lifecycle callback via Jakarta annotation | Depends on valid signature and Spring processor |
| **@Bean(destroyMethod)** | Specify/infer cleanup method from bean metadata | Per selected method |

If a bean's lifecycle is **owned by Spring**, Spring can call close when closing the context. Implementing `AutoCloseable` **does not** cause the JVM to call close automatically if you merely write **new Resource()** and discard the reference. Cleanup responsibility depends on **who actually owns the resource**.

## 3. How Does @Bean Infer a Destroy Method by Default?

The **org.springframework.context.annotation.Bean** annotation has the attribute:

~~~java
String destroyMethod() default "(inferred)";
~~~

This is an abbreviated signature from the Spring Framework 6.2 Javadoc, not a method call in application code. The special default value **"(inferred)"** instructs the container to look for a suitable destroy method.

In Spring Framework 6.2, the inference scope per the Javadoc covers **public no-argument methods named `close` or `shutdown`**, even if inherited from a superclass. Beans implementing **AutoCloseable** or **Closeable** match naturally because they have **close()**.

**Example 1 — bean implementing AutoCloseable:**

~~~java
final class FileLikeClient implements AutoCloseable {
    @Override
    public void close() {
        System.out.println("FileLikeClient.close()");
    }
}

@Bean
FileLikeClient fileLikeClient() {
    return new FileLikeClient();
}
~~~

These are two illustrative snippets placed in appropriate classes, not a standalone runnable file. Because the **@Bean** method uses the default `destroyMethod`, the container can automatically register the **close()** callback.

**Example 2 — bean not implementing AutoCloseable but having shutdown():**

~~~java
final class BackgroundClient {
    public void shutdown() {
        System.out.println("BackgroundClient.shutdown()");
    }
}

@Bean
BackgroundClient backgroundClient() {
    return new BackgroundClient();
}
~~~

A public, no-argument **shutdown()** method can be inferred as a destroy method even when the class does not implement `AutoCloseable`.

**Example 3 — custom cleanup() method:**

~~~java
final class LegacyClient {
    public void release() {
        System.out.println("LegacyClient.release()");
    }
}

@Bean(destroyMethod = "release")
LegacyClient legacyClient() {
    return new LegacyClient();
}
~~~

Because the method is named **release**, Spring **does not infer this name automatically**; you must declare **destroyMethod = "release"** explicitly.

**Inference limits:** do not assume Spring tries arbitrary method names like **dispose, clear, delete, or terminate**. With default `@Bean`, the documented inferred names are only public, no-argument **close** or **shutdown**. For any other method name, specify it explicitly.

### Does Spring inspect the declared return class or the actual instance?

One detail in the Javadoc: detection can reflect on **the class of the created bean instance**, not necessarily restricted to the declared return type of the `@Bean` method.

Example:

~~~java
interface Client {
    void request();
}

final class RealClient implements Client, AutoCloseable {
    @Override
    public void request() {
    }

    @Override
    public void close() {
        System.out.println("RealClient.close()");
    }
}

@Bean
Client client() {
    return new RealClient();
}
~~~

This is an illustrative snippet that must be placed in a project with valid classes/imports. Even though the **@Bean** method returns the **Client** interface without declaring `close`, the actual instance is **RealClient**, which has a public `close` and implements `AutoCloseable`. Per the `@Bean` 6.2 Javadoc, inference can detect that instance's method.

However, do not build a cleanup design that depends on proxies, factories, or uncontrolled runtime classes. For APIs you clearly own, **implementing AutoCloseable** or **explicitly declaring destroyMethod** makes the contract easier to understand.

## 4. When Does Destruction Run?

For **singleton beans under the full management of ApplicationContext**, destruction callbacks typically run during context **close()**, including when Spring Boot performs a normal shutdown.

Simple timeline:

~~~text
SpringApplication.run(args)
        |
        v
Create ApplicationContext
        |
        v
Register/parse BeanDefinitions, refresh
        |
        v
Create singleton bean instance
        |
        +--> @PostConstruct / init callbacks
        |
        v
Application running
        |
        v
ApplicationContext.close()
        |
        +--> Stop Lifecycle / SmartLifecycle components
        |
        +--> Destroy singleton beans per dependency/lifecycle
        |      @PreDestroy
        |      DisposableBean.destroy() (if present)
        |      inferred/explicit custom destroy method
        |
        v
Context closes, resources are released
~~~

An initialized bean **is not automatically destroyed right after the `@Bean` factory method returns**. Destruction is tied to scope termination and the container's contract.

### Spring Boot web application case

In a long-running Spring Boot application, `SpringApplication` typically registers a JVM shutdown hook to close the context on normal JVM shutdown. Therefore **you do not need to manually call `close()` on each singleton bean** if it is owned by the context and callbacks are properly configured.

However, there is **no absolute guarantee** if the process receives **SIGKILL**, the machine loses power, the JVM crashes, or the container is force-killed before the termination grace period expires. Business data design and side-effect handling must tolerate cases where cleanup does not run.

### Difference from garbage collection

The garbage collector manages heap memory; it is not a complete substitute for closing sockets, file descriptors, connection pools, or flushing/acking messages. **AutoCloseable is not a finalizer**, and an inferred destroy method does not run simply because an object becomes "unreferenced." It is a callback from **Spring BeanFactory when a bean is properly destroyed**.

## 5. Three Ways to Configure destroyMethod

| Declaration | Meaning | Application Example |
| --- | --- | --- |
| **@Bean** | Uses default **"(inferred)"** to find public no-arg `close`/`shutdown` | Spring-owned client/pool |
| **@Bean(destroyMethod = "close")** | Explicitly specifies `close` as the destroy method | Wanting an explicit contract |
| **@Bean(destroyMethod = "shutdown")** | Explicitly specifies `shutdown` | Scheduler/service with `shutdown` |
| **@Bean(destroyMethod = "release")** | Specifies another method provided by the class | Legacy SDK with `release` |
| **@Bean(destroyMethod = "")** | Disables custom `close`/`shutdown` inference for this bean | Resource managed by an external owner |

### What does destroyMethod="" actually disable?

Per the `@Bean` 6.2 Javadoc, writing:

~~~java
@Bean(destroyMethod = "")
ExternalClient externalClient() {
    return externallyManagedClient;
}
~~~

stops Spring from **inferring a call to `close` or `shutdown`** on this bean merely because it has a matching method. However, it **does not mean disabling every destruction mechanism**.

Specifically:

- If the bean implements **DisposableBean**, Spring can still detect and invoke the **destroy()** callback.
- If the bean has a **@PreDestroy** method, the corresponding lifecycle processing can still invoke it.
- If the bean implements **SmartLifecycle**, the **stop** phase is a separate contract and can run before destroy callbacks.
- If a scope or custom scope has its own destruction mechanism, check the scope/`BeanFactory` contract.

Therefore **@Bean(destroyMethod = "")** is a tool for **disabling inferred custom `close`/`shutdown`**, not a "master switch to disable all cleanup."

### When should inference be disabled?

Suppose an application receives a shared HTTP client from another framework:

~~~java
@Bean(destroyMethod = "")
SharedHttpClient sharedHttpClient() {
    return externalClientRegistry.getSharedClient();
}
~~~

This is an illustrative snippet requiring real types and a real registry. If Spring only **borrows** the client while another system keeps using it after the context closes, Spring should not close that client automatically. **The external owner** is responsible for closing it at the right time.

Conversely, if Spring **creates a new client** in a factory method and owns that client, using default **@Bean** to close the resource automatically is usually simpler and safer.

**Do not use `destroyMethod=""` to hide slow cleanup or exceptions.** If Spring truly owns the resource, disabling close can leave sockets, worker threads, or connection pools unreleased.

## 6. Runnable Java 17+ Example: Verifying Inference and Resource Ownership

This example creates a **non-web** Spring Boot application with two beans:

1. **TrackedResource** created by Spring, implementing **AutoCloseable** and having **@PreDestroy**. No `destroyMethod` is specified; Spring infers `close` when the context closes.
2. **BorrowedChannel** created by an owner outside `BeanFactory`, which Spring only borrows to register as a bean. The `@Bean` method sets **destroyMethod = ""** to prevent Spring from closing it automatically; the owner itself closes it after the context closes.

The goal is to observe the callback order **deterministically**, without depending on the destruction order of dozens of other beans.

### 6.1. Create the project

Using **Spring Initializr**, choose:

- **Maven**, **Java 17+**.
- **Spring Boot 3.5.x**.
- Group **com.example**, artifact **bean-cleanup-demo**, package **com.example.demo**.
- Dependency **Spring Boot Starter**.

Spring Web is not needed. Keep the POM and Maven Wrapper generated by Initializr. Java 17+ matches Spring Framework 6.2 and the **jakarta.annotation.PreDestroy** package.

### 6.2. Complete Java file

Create **src/main/java/com/example/demo/BeanCleanupDemoApplication.java**:

~~~java
package com.example.demo;

import jakarta.annotation.PreDestroy;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class BeanCleanupDemoApplication {

    // Demo: main is the owner; Spring only borrows this instance.
    private static final BorrowedChannel EXTERNAL_CHANNEL =
            new BorrowedChannel();

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(BeanCleanupDemoApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);

        System.out.println("01 | before run");

        try (ConfigurableApplicationContext context = app.run(args)) {
            // Regular singletons were already created during refresh.
            context.getBean(TrackedResource.class);
            System.out.println("03 | context active="
                    + context.isActive());
        }

        System.out.println("06 | context closed");

        // Only the owner outside BeanFactory closes the borrowed resource.
        EXTERNAL_CHANNEL.close();
        System.out.println("08 | external owner finished");
    }

    @Bean
    TrackedResource trackedResource() {
        return new TrackedResource();
    }

    @Bean(destroyMethod = "")
    BorrowedChannel borrowedChannel() {
        return EXTERNAL_CHANNEL;
    }

    static final class TrackedResource implements AutoCloseable {

        TrackedResource() {
            System.out.println("02 | TrackedResource created");
        }

        @PreDestroy
        void beforeDestroy() {
            System.out.println("04 | @PreDestroy");
        }

        @Override
        public void close() {
            System.out.println("05 | inferred close()");
        }
    }

    static final class BorrowedChannel implements AutoCloseable {

        private boolean closed;

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                System.out.println("07 | owner closes BorrowedChannel");
            }
        }
    }
}
~~~

**Why does this example compile?**

- The public class **BeanCleanupDemoApplication** matches the filename.
- **@SpringBootApplication** and **@Bean** come from the Spring Boot/Framework dependencies provided by the starter.
- **@PreDestroy** is the Jakarta annotation; do not use the legacy Java 8 **javax.annotation** package.
- Both inner classes are **static nested classes**, so `@Bean` factory methods can instantiate them without needing an outer instance per resource.
- **TrackedResource.close()** is public per the `AutoCloseable` contract and is inferred by Spring.
- **BorrowedChannel** also has a public `close`, but its bean definition sets **destroyMethod = ""** to prevent inference.
- `main` uses **try-with-resources** with **ConfigurableApplicationContext**; upon exiting the block, Java calls `context.close()`, and Spring invokes destruction callbacks on the beans it owns.
- It does not create resources with **new** and forget cleanup; the borrowed resource is explicitly closed by its owner after the context closes.

**Important note:** the example assumes `TrackedResource` is a non-lazy singleton as by default. If you change its scope to prototype or mark it lazy and never instantiate it, the callback behavior differs; Section 10 analyzes that case.

### 6.3. Run it

From the Maven directory:

~~~bash
# Linux/macOS
./mvnw spring-boot:run

# Windows PowerShell/cmd:
# .\mvnw.cmd spring-boot:run
~~~

Lines **explicitly printed by the program**, in order:

~~~text
01 | before run
02 | TrackedResource created
03 | context active=true
04 | @PreDestroy
05 | inferred close()
06 | context closed
07 | owner closes BorrowedChannel
08 | external owner finished
~~~

Spring Boot/Maven may print additional logs; these are the filtered demo lines. Since no other beans print similar numbered lines and `close` is called synchronously, the order of these lines is deterministic during a successful startup/shutdown.

**Interpretation:**

- **01:** `main` before `SpringApplication.run`.
- **02:** Spring instantiates `TrackedResource` during refresh.
- **03:** `SpringApplication.run` has returned; the context is still active.
- **04:** When closing the context, Spring processes `@PreDestroy` on `TrackedResource`.
- **05:** The inferred destroy method calls `close()` on `TrackedResource` after `@PreDestroy`.
- **06:** `context.close` has completed.
- **07:** The owner outside the container explicitly closes `BorrowedChannel`; this is **not** a callback triggered by Spring.
- **08:** `main` finishes.

Line **07** happens only because `main` **explicitly calls** `EXTERNAL_CHANNEL.close()`. If you remove that call, Spring **will not close `BorrowedChannel`** because `destroyMethod` was disabled; the owner must have its own management policy.

### 6.4. Variants to test destroyMethod yourself

**Variant A — enable inference for BorrowedChannel.** Change:

~~~java
@Bean(destroyMethod = "")
BorrowedChannel borrowedChannel() {
    return EXTERNAL_CHANNEL;
}
~~~

to:

~~~java
@Bean
BorrowedChannel borrowedChannel() {
    return EXTERNAL_CHANNEL;
}
~~~

When the context closes, Spring can invoke **BorrowedChannel.close()**; if `main` still closes it afterward, the method can be called twice. The demo class has a **closed** guard so it only prints line 07 once, **but that does not prove `close` was only called once**. This is why you must not transfer ownership casually: a real HTTP client may behave differently when closed twice.

**Variant B — disable inference for TrackedResource.** Change:

~~~java
@Bean
TrackedResource trackedResource() {
    return new TrackedResource();
}
~~~

to:

~~~java
@Bean(destroyMethod = "")
TrackedResource trackedResource() {
    return new TrackedResource();
}
~~~

When closing the context, **@PreDestroy still runs**, but **inferred `close()` is no longer invoked by default**. This is an important example: **destroyMethod = "" does not disable @PreDestroy**, yet it can leave a real resource unclosed if no other owner closes it.

Do not apply both variants simultaneously while expecting the original example's stdout to stay identical.

## 7. @Bean(destroyMethod = "shutdown") and shutdown() Inference

If a class does not implement `AutoCloseable` but has a public no-argument **shutdown()**, Spring can still infer it in default mode.

~~~java
public final class MessageClient {
    private boolean running = true;

    public void send(String value) {
        if (!running) {
            throw new IllegalStateException("already shut down");
        }
        System.out.println("send: " + value);
    }

    public void shutdown() {
        if (running) {
            running = false;
            System.out.println("MessageClient.shutdown()");
        }
    }
}
~~~

This is a syntactically standalone Java class, though to use it as a Spring bean, declare it inside a configuration class:

~~~java
@Bean
MessageClient messageClient() {
    return new MessageClient();
}
~~~

Or if you want to be explicit:

~~~java
@Bean(destroyMethod = "shutdown")
MessageClient messageClient() {
    return new MessageClient();
}
~~~

**The two `@Bean` snippets are mutually exclusive alternatives**; do not declare both with the same name in one configuration. When `ApplicationContext` closes and owns this singleton, Spring can call `shutdown()`.

### When the cleanup method is not close/shutdown

An SDK may use **disconnect()** or **release()**. Spring does not infer those names automatically; choose:

~~~java
@Bean(destroyMethod = "disconnect")
LegacyConnection legacyConnection() {
    return new LegacyConnection();
}
~~~

This illustrative snippet requires the **LegacyConnection** class to actually have a matching **disconnect()** method. Specifying a nonexistent method name can cause lifecycle/bean-creation or destroy-callback configuration errors depending on API and phase; do not treat it as a no-op option.

### Do you need to write destroyMethod = "(inferred)" explicitly?

Usually **no**: `@Bean` already defaults to **"(inferred)"**. Writing this value explicitly can help communicate intent, but it does not make detection any stronger.

## 8. Order of @PreDestroy, DisposableBean, and Custom Destroy Methods

A bean can participate in multiple destruction mechanisms:

1. Methods annotated with **@PreDestroy**.
2. Spring's **DisposableBean.destroy()** (if implemented).
3. Configured or inferred custom destroy method, such as **close()**.

The Spring Framework Reference describes the order above when these mechanisms are configured using **distinct methods**.

~~~text
ApplicationContext.close()
    |
    +--> @PreDestroy
    |
    +--> DisposableBean.destroy()
    |
    +--> custom/inferred destroy method
         close() / shutdown() / release()
~~~

Example illustrating the signatures:

~~~java
class CombinedResource implements DisposableBean, AutoCloseable {

    @PreDestroy
    public void beforeDestroy() {
        System.out.println("@PreDestroy");
    }

    @Override
    public void destroy() {
        System.out.println("DisposableBean.destroy()");
    }

    @Override
    public void close() {
        System.out.println("AutoCloseable.close()");
    }
}
~~~

This **is not a standalone Java file**: you must import **jakarta.annotation.PreDestroy** and **org.springframework.beans.factory.DisposableBean**, and register the bean with the context. In cases where a bean implements `DisposableBean`, Spring has logic to avoid duplicate callback registration when inferring destroy methods; **do not treat this snippet as a promise that Spring always invokes both `destroy()` and `close()`**. For predictable cleanup, choose one clear contract instead of stacking multiple methods and guessing the order.

**Practical rule:** never have two different callbacks release the same non-idempotent resource. If multiple callbacks are unavoidable, each must have a distinct responsibility, or the cleanup method must be safe under repeated calls.

### One method declared through multiple mechanisms

Spring has logic to avoid invoking the exact same method repeatedly when callbacks overlap. Still, do not rely on reflection order, AOP proxies, or an assumption like "always calls `close` exactly twice." Test empirically whenever a bean implements multiple lifecycle interfaces simultaneously.

### @PreDestroy does not infer the name close

If you have:

~~~java
@PreDestroy
public void cleanUpBeforeShutdown() {
    // ...
}
~~~

this callback is registered via Jakarta annotation processing. It is **different** from an inferred destroy method matched by the name `close`/`shutdown`. Both can coexist and perform **separate tasks**.

## 9. Difference Between stop and destroy

Some resources do not just close a socket; they also have background threads that must be stopped in a controlled way. Spring provides **Lifecycle** and **SmartLifecycle** to manage start/stop ordering, whereas destroy methods handle the final release step.

Example:

~~~text
Context active
     |
     v
ApplicationContext close requested
     |
     +--> SmartLifecycle.stop(Runnable)
     |    Stop accepting work, wait for in-flight tasks
     |    callback.run() when stopped
     |
     +--> @PreDestroy / DisposableBean.destroy
     |
     +--> Inferred close() or explicit shutdown()
     |    Close connections, release final resources
     |
     v
Context closes
~~~

**SmartLifecycle.stop(Runnable)** has a callback contract and phase-based ordering; inferring **close()/shutdown()** does not replace that mechanism. If a bean has background processing threads, separate:

- **Quiesce:** stop accepting new work.
- **Drain:** wait for running work with an appropriate deadline.
- **Dispose:** close the resource.
- **Confirm:** report completion and record metrics.

Do not assume that simply implementing `AutoCloseable.close()` makes Spring wait for every `Future` to finish. The `close` method must implement the proper contract itself or coordinate via lifecycle phases.

**A common hazard:** one bean closes the HTTP client in `@PreDestroy` or inferred `close` while a consumer in another phase still needs that client to flush. Align dependencies/`SmartLifecycle` phases and graceful shutdown budgets properly.

## 10. Bean Scope Determines Whether the Container Destroys Instances

### Singleton (default)

For normal singleton beans managed by `ApplicationContext`, the container holds a reference and registers destruction callbacks. When the context closes normally, Spring invokes the appropriate callbacks. That is the case in the Section 6 demo.

If a singleton bean has **@Lazy**, it may only be initialized when first accessed. When no instance was ever created, naturally there is no concrete instance to close; do not claim that every `@Bean` definition leads to a close call.

### Prototype

With **@Scope("prototype")**, Spring creates and initializes each requested instance, but **does not manage the complete destruction lifecycle** of prototypes after returning them to the caller.

~~~java
@Bean
@Scope("prototype")
ResourceSession resourceSession() {
    return new ResourceSession();
}
~~~

This is an illustrative configuration snippet requiring the `ResourceSession` class and `Scope` import. If each `getBean` call creates a new `ResourceSession` implementing `AutoCloseable`, **the caller is responsible for closing that instance**.

Usage example:

~~~java
try (ResourceSession resource =
        context.getBean(ResourceSession.class)) {
    resource.perform();
}
~~~

This is an illustrative snippet requiring the `context` variable, a `ResourceSession` class implementing `AutoCloseable`, and a `perform` method. Do not infer that Spring automatically closes every prototype when `ApplicationContext` closes.

### Request/session/custom scopes

Scopes like request/session have lifecycles and destruction callbacks tied to the end of that scope, not simply `ApplicationContext.close`. A custom scope must manage registering/invoking destruction callbacks per its contract. Evaluate scope type and lifetime carefully in your application; do not swap singleton/prototype for another scope while keeping the same cleanup assumptions.

### Objects not created by Spring

If code executes:

~~~java
ResourceSession resource = new ResourceSession();
~~~

without putting that object into the bean container, Spring has no knowledge of the object to call any destroy method. **AutoCloseable** is just a Java contract; the Java code that creates the object must use `try-with-resources` or close it in the appropriate place.

## 11. Resource Ownership Matters More Than Having a close Method

A more useful architectural question than "does this class have `close`?" is **"who owns the right to end this resource's lifecycle?"**

| Resource Origin | Who Should Close It? | Usually Appropriate Configuration |
| --- | --- | --- |
| Singleton newly created in `@Bean`, used exclusively within context | Spring `ApplicationContext` | Default `@Bean` infers `close`/`shutdown` |
| Singleton SDK client created by Spring needing non-standard cleanup | Spring `ApplicationContext` | `@Bean(destroyMethod = "release")` |
| Instance owned by another host/plugin container, only borrowed by Spring | Host/plugin container | `@Bean(destroyMethod = "")` if only disabling inferred close |
| Prototype created per task invocation | Caller receiving the instance | `try-with-resources` / manual close |
| Resource created in a local method, not registered as a bean | Creating method/caller | `try-with-resources` |
| Client/pool shared across multiple `ApplicationContext`s | Explicitly designated single owner | Avoid having each context close the shared instance |
| Resource managed by a library with its own lifecycle | Check library contract | Do not assume and call close twice |

### Hazard: multiple contexts returning the same instance

Suppose context A and context B both register the same **sharedClient** object from default `@Bean` methods. If one context closes first, it may call **sharedClient.close()** even though the other context still needs the client.

This is an **ownership** issue, not an inference bug. Sharing a resource across multiple contexts requires a clear owner, reference counting, or centralized lifetime; you can set **destroyMethod=""** in borrowing contexts while the true owner still closes it last.

### Hazard: automatic close losing in-flight data

A message sender has a **shutdown()** method, so automatic Spring inference is reasonable if the sender is owned solely by the context. However, the library's **shutdown()** might not flush all in-flight messages or may have its own timeout. Spring calling the method on time **does not replace** graceful shutdown policies and delivery guarantees. You must still read the SDK contract, design draining/flushing, and test under `SIGTERM`.

## 12. Why Should You Not Expose a "Borrowed" Resource Without Disabling Inference?

Common pattern:

~~~java
@Bean
AutoCloseable externalResource() {
    return ExternalRegistry.getSharedResource();
}
~~~

If the actual object has a **public close()**, default `@Bean` can infer `close`. When the context closes, Spring will close the object even though it is a shared resource of an external host.

Safer intentional pattern:

~~~java
@Bean(destroyMethod = "")
AutoCloseable externalResource() {
    return ExternalRegistry.getSharedResource();
}
~~~

Both snippets are **illustrative design patterns** requiring a real `ExternalRegistry` and bean contract. The second option prevents inferred close. Yet if the object itself also implements **DisposableBean** or has **@PreDestroy**, you must check those other callbacks; `destroyMethod=""` **is not an all-encompassing cancellation mechanism**.

### Avoid using @Bean(destroyMethod="") out of fear of errors

Do not disable cleanup just because you see "Connection closed" in shutdown logs without finding the root cause. That error could stem from:

- Wrong dependency stop order.
- Client closed by two different owners.
- A thread continuing to use the client after shutdown began.
- Code calling `close` prematurely.
- Insufficient shutdown time.
- Library not handling idempotent `close`.

If the client is genuinely owned by Spring, the fix is **fixing ownership and shutdown order**; unconditionally disabling inference can cause resource leaks.

## 13. Common Pitfalls with Inferred Destruction

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Bean calls `close` even without `destroyMethod` | `@Bean` defaults to `"(inferred)"` | Check public no-arg `close`/`shutdown` on the actual class |
| Wanted `release()` called, but it never ran | Not among the inferred names | Declare `@Bean(destroyMethod = "release")` |
| `@Bean(destroyMethod = "")` yet `@PreDestroy` still runs | Different lifecycle mechanism | Check and design each callback separately |
| `@Bean(destroyMethod = "")` yet `DisposableBean.destroy` still runs | Interface callback is not disabled by that attribute | Avoid exposing this resource as a bean if callbacks are unwanted |
| `AutoCloseable` prototype does not close when context closes | Prototypes do not have full container destruction tracking | Caller closes it or uses a custom scope |
| `@Lazy` bean never created so `close` is never seen | No concrete instance exists | Avoid tests assuming every definition is instantiated |
| Class has private `cleanup()` yet Spring does not infer it | Only looks for public no-arg `close`/`shutdown` | Adjust method/visibility and declare explicitly |
| Class has `public shutdown(int)` yet it never runs | Has parameters, ineligible for inference | Change contract or use an explicit adapter |
| `getBean` returns an interface without `close`, yet it still closes | Inference inspects the actual bean instance | Read Javadoc; do not inspect only the return type |
| Resource closed twice | Multiple owners or uncontrolled duplicate callbacks | Use a single owner and idempotent `close` |
| No cleanup when process receives `SIGKILL` | Orderly shutdown did not run | Design recovery/idempotency; do not rely solely on `@PreDestroy` |
| `@Component` has `close` yet behaves differently from `@Bean` | Different registration source/bean definition metadata and interfaces | Check the actual lifecycle mechanism; do not assume all beans behave identically |
| Shutdown takes many more seconds than expected | Blocking `close`/I/O lacks deadlines | Design client timeouts, `SmartLifecycle`, and graceful budgets |
| Spring closes a shared client too early | Default `@Bean` handed a borrowed resource | Transfer ownership or intentionally disable inferred close |

### Logging and verifying cleanup

When investigating whether a bean is closed, you can log:

- Bean name and timestamp when the context closes.
- Actual destroy method invoked.
- How many tasks remain in flight.
- Resource state before/after close.
- Exceptions/`elapsedMillis` during cleanup.
- Dependency chain and phase if using `SmartLifecycle`.

Never log secrets, credentials, payloads, or `object.toString()` outputs that might expose sensitive data.

## 14. Practical Testing

### 14.1. Testing close inference

Create a singleton `@Bean` with a public `close` and close the context normally. You can use an **AtomicBoolean** to record the close:

~~~java
final class CloseProbe implements AutoCloseable {

    private final AtomicBoolean closed = new AtomicBoolean();

    @Override
    public void close() {
        closed.set(true);
    }

    boolean isClosed() {
        return closed.get();
    }
}
~~~

This is an illustrative Java snippet requiring import of **java.util.concurrent.atomic.AtomicBoolean**. Expected test result:

~~~text
Before context.close(): closed=false
After context.close():  closed=true
~~~

To test accurately, retain a reference to the bean before closing the context and inspect it after close. Do not call `getBean` on an already closed context.

### 14.2. Testing destroyMethod="" with a borrowed resource

Pass a borrowed resource to `@Bean(destroyMethod="")`, close the context, and verify **closed remains false**. Then have the owner call `close` and verify true. Use a resource with no other callbacks (neither `DisposableBean` nor `@PreDestroy`) if your test specifically targets **the inferred close mechanism alone**.

### 14.3. Testing callback order

For a bean with both `@PreDestroy` and `AutoCloseable.close` and no `DisposableBean`, the Spring Framework Reference gives the order:

~~~text
@PreDestroy
close() inferred from @Bean
~~~

Tests should avoid depending on destruction order **across independent beans**, since dependency graphs and bean registration order can vary by environment. Assert callback order **within the same bean** under the proper contract.

### 14.4. Testing failure paths

Simulate `close()` throwing a controlled exception. The application should log the failing bean/method and continue subsequent shutdown steps according to container behavior. Do not expect cleanup to always complete if a callback blocks indefinitely or the JVM receives `SIGKILL`.

### 14.5. Testing resource ownership

Same client returned to two contexts: intentionally close context A first, then try using the client from context B. If the resource closes itself and causes an error, the architecture has an ownership conflict. The fix is not increasing shutdown timeout, but assigning a clear owner and preventing auto-close in borrowing contexts.

## 15. Self-Check Questions

**Question 1.** Why does implementing `AutoCloseable` not mean the JVM calls `close` automatically when GC reclaims an object?

**Question 2.** A bean is created from `@Bean` without specifying `destroyMethod`; the actual class has `public shutdown()` but does not implement `AutoCloseable`. Can Spring call `shutdown` when the context closes?

**Question 3.** Why is `public release()` not inferred like `public close()` or `public shutdown()`?

**Question 4.** When writing `@Bean(destroyMethod = "")`, does this disable `@PreDestroy` and `DisposableBean.destroy`?

**Question 5.** Why can't "a managed singleton bean" and "a prototype handed to a caller" be treated as having the same destruction policy?

**Question 6.** An external service is shared between two contexts, and two `@Bean` methods use default inference. What is the risk when the first context closes?

**Question 7.** A `@Bean` factory method returns an interface type without `close`, while the actual instance implements `AutoCloseable`. Will inference definitely miss `close` because the return type does not declare it?

**Question 8.** In the demo, why is line **07** not a Spring callback?

**Question 9.** A client implements both `SmartLifecycle` and `AutoCloseable`. Why should `stop` and `close` have separate responsibilities?

**Question 10.** If the JVM is killed immediately, can `@PreDestroy` or inferred `close` be guaranteed to run?

### Suggested Answers

1. `AutoCloseable` is an API contract; `close` is called by an owner such as `try-with-resources` or bean lifecycle, not automatically by GC.
2. Yes, if it is a public no-arg `shutdown` and the bean falls under the appropriate scope/destruction contract.
3. The name `release` is not in the inferred list; `destroyMethod` must be declared explicitly.
4. No; it only disables inferred custom `close`/`shutdown`, while other callbacks retain their own semantics.
5. The container tracks singleton destruction, whereas prototypes are normally closed by the caller.
6. Context A can close the resource while context B is still using it.
7. No; the `@Bean` Javadoc states detection is based on the actual instance.
8. `main` is the owner of `BorrowedChannel` and calls `EXTERNAL_CHANNEL.close()` after the context has closed.
9. `stop` suits stopping intake/draining tasks by phase; `close` suits final resource disposal.
10. No; `SIGKILL` and crashes can bypass orderly shutdown.

## 16. Design Checklist Before Using @Bean

- [ ] Is the resource **genuinely owned** by the Spring `ApplicationContext`?
- [ ] Is the bean scope singleton, prototype, or a custom scope?
- [ ] If implementing `AutoCloseable`/`Closeable`, does `close` have the proper public no-arg contract?
- [ ] If it only has `shutdown()`, is the method public and parameterless?
- [ ] If the cleanup method has another name, is `destroyMethod` explicitly declared?
- [ ] If the bean returns an external resource, is `destroyMethod=""` needed?
- [ ] Have other `@PreDestroy`/`DisposableBean`/`SmartLifecycle` callbacks been checked?
- [ ] Is close/destroy idempotent and safe under partial initialization failures?
- [ ] Do required dependencies live long enough for cleanup?
- [ ] Are bounded network timeouts and matching termination grace periods configured?
- [ ] Has it been verified on the actual Spring Framework/Boot version in use?
- [ ] Are tests written for closing the context, not just for creating the bean successfully?
- [ ] Has production shutdown been tested with `SIGTERM` and force-kill scenarios?
- [ ] Do you avoid depending on destruction order between unrelated singletons?

## 17. Summary and Official References

**AutoCloseable** defines how an object releases resources, while **@Bean** specifies how that object participates in the Spring lifecycle. Spring Framework defaults to **destroyMethod = "(inferred)"** for `@Bean` and can automatically invoke public no-arg **close()** or **shutdown()** when the container destroys a bean it manages.

- **@Bean**: convenient when Spring owns the resource and the class has `close`/`shutdown`.
- **@Bean(destroyMethod = "release")**: explicitly uses another method name.
- **@Bean(destroyMethod = "")**: disables inferred `close`/`shutdown`, appropriate when Spring only borrows the resource; does not disable all lifecycle callbacks.
- **Singleton**: normally has destruction managed by the container when the context closes cleanly.
- **Prototype**: the caller is responsible for cleanup; Spring does not automatically close every instance on context close.
- **@PreDestroy**, **DisposableBean**, and **SmartLifecycle** are distinct mechanisms and must be coordinated properly.
- **SIGKILL/crashes** can bypass cleanup; do not treat destruction callbacks as the sole guarantee of data safety.

Official sources, referencing Spring Framework 6.2 / Spring Boot 3.5:

1. Spring Framework 6.2 Javadoc — `@Bean.destroyMethod` and default `"(inferred)"`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/Bean.html
2. Spring Framework Reference — Using the `@Bean` Annotation: https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html
3. Spring Framework Reference — Customizing the Nature of a Bean: https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html
4. Spring Framework Reference — Bean Scopes and prototype destruction: https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html
5. Oracle Java 17 — `AutoCloseable`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html
6. Spring Boot 3.5 — `SpringApplication` startup/shutdown: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html

The runnable example uses **Java 17+**, **Spring Boot 3.5.x**, and **Spring Framework 6.2.x**. When using other versions or client SDKs, check the exact Javadoc and actual resource contract before deciding who calls `close()`.