# Impact of private, final, and Call Interception Capability in Spring Concurrency

In the Spring Framework, when a method is annotated with **@Async**, asynchronous execution usually does not happen because of the annotation itself or because a Java keyword switches threads. In the default **proxy-based** mode, Spring creates a **proxy** in front of the bean. Only a call passing **through the proxy** has the chance to be recognized by the interceptor/advice, dispatched to a **TaskExecutor**, and returned to the caller under the async contract.

Therefore, **private**, **final**, the proxy type, and the **call path** directly affect interception capability:

- A **private method** cannot be called through the proxy's public surface and cannot be overridden by a class-based proxy for interception.
- A **final method** cannot be overridden by a **class-based (CGLIB) proxy**. However, a **JDK interface proxy** can intercept a call going through the **interface**, even if the target's implementing method is declared **final**; this is an important distinction.
- A **final class** cannot be subclassed by CGLIB. Nevertheless, a **final class implementing an interface** can still be wrapped by a **JDK interface proxy**, provided the configuration and calls go through the interface.
- **Self-invocation**, such as **this.work()** or calling a method name without `this` inside the same bean, normally **bypasses the proxy**, even when `work()` is public and non-final.
- Having an **interceptable public method** does not mean every call to it is intercepted: you must check whether the caller holds the **proxy or the target**.

This Knowledge lesson belongs to the **Proxy and Invocation** group in **Spring Framework - concurrency**. Its focus is understanding why **@Async does not run on a worker as expected**, how to analyze call paths, verify behavior with Java 17, choose proxy types, and fix code structure safely.

## 1. Where Does the Proxy Sit in the Call Path?

An ordinary Java object performs direct calls:

~~~text
Caller ----> service instance ----> service.work()
~~~

In Spring AOP in proxy mode, the bean handed to the caller may be a **proxy**, not the raw target object:

~~~text
                         call through proxy
Caller ----> Proxy ----> Async interceptor ----> Executor
                 |                                 |
                 |                                 +-- worker thread:
                 |                                      target.work()
                 |
                 +-- may return Future/CompletableFuture

When target calls this.work():
target ------> target.work()         (does not go back through Proxy)
~~~

This path explains two important phenomena:

1. **The annotation alone is not enough.** Spring must enable async support, the bean must be Spring-managed, and the call must pass through a structure the interceptor can intercept.
2. **A call into the target from inside the target does not automatically loop back through the proxy.** The issue does not lie in the method name or logic complexity; it is the call-dispatch characteristic of proxy-based AOP.

At the JDK level, Spring can use a **JDK dynamic proxy** (standing on interfaces) or a **CGLIB subclass proxy** (generating a subclass of the target). Both approaches are proxies, yet their technical limits differ.

**Lesson scope:** explains the proxy-based **@Async** mechanism, while pointing out proxy limitations that also commonly affect **@Transactional**, **@Cacheable**, and other AOP advice. Do not treat all annotations or all Spring versions as identical: they have their own annotation-detection rules, method visibility scopes, and configurations.

## 2. private in Java and Why the Proxy Cannot Intercept It

A **private method** is directly accessible only inside the class that declares it, under Java access rules. When a public method calls a private helper, the private call is resolved inside the object; it **does not become a call going through the proxy merely because the private method has @Async**.

~~~java
import org.springframework.scheduling.annotation.Async;

public class InvoiceService {
    public void submitInvoice() {
        sendInBackground(); // Internal call, does not pass through proxy.
    }

    @Async
    private void sendInBackground() {
        // Not intercepted by a Spring proxy to switch to another thread.
    }
}
~~~

This is an **illustrative snippet within a Spring application**; it is not a standalone Java file. With proxy-based async:

- CGLIB creates a subclass to intercept overridable methods; **private methods cannot be overridden** in Java, so the proxy cannot insert an interceptor on this call.
- A JDK proxy only exposes methods belonging to the **proxied interface**, never creating a private call entry point on the implementation for callers.
- Placing the annotation on a private method **does not turn an internal call into an async call**.
- If **submitInvoice()** is called directly from a request thread, the private helper normally runs on that same thread unless code explicitly uses an executor elsewhere.

**What to avoid:** stepping through a debugger, seeing `@Async` on a private method, and assuming it submitted a task; verify **Thread.currentThread()** or test thread-identity correlation.

### When Can a private Helper Still Run on a Worker?

If **a public method is intercepted by the proxy and dispatched to an executor**, that public method can invoke a private helper *inside the worker*. This is valid and useful:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {
    @Async("notificationExecutor")
    public void deliver(String recipient) {
        validateAndSend(recipient); // Runs on the thread executing deliver.
    }

    private void validateAndSend(String recipient) {
        // Internal helper; does not need its own @Async.
    }
}
~~~

**deliver** must be **called by another bean through the proxy** and async support configuration must be valid. The **validateAndSend** helper is called from the body of `deliver`, meaning it can run on the worker after `deliver` is dispatched; **not** because the proxy intercepted the private helper.

Keep the two ideas separate:

- "Is a private method independently intercepted by a Spring AOP proxy?" → **No**.
- "Can a private helper execute inside a worker when called by a public `@Async` method?" → **Yes**, if the public `@Async` method was genuinely dispatched.

That is why **moving @Async from a private helper to a public entry point** often resolves the bug, provided callers invoke the public entry point through the proxy.

## 3. final Methods: Cannot Be Overridden by CGLIB

A **final method** in Java prevents subclasses from overriding it. A CGLIB class-based proxy works by creating a subclass of the target and then **overriding overridable methods** to insert advice into the call path.

Therefore, a **public final** method cannot be intercepted by CGLIB using overriding:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;

public class BillingService {
    @Async("billingExecutor")
    public final CompletableFuture<String> calculate() {
        return CompletableFuture.completedFuture("ready");
    }
}
~~~

This is an **illustrative snippet**, not a complete runnable program. When Spring uses a **class-based proxy**, **calculate()** is `final`, so the interceptor cannot override that method to dispatch it to the executor. Calls to the final method can go straight to the Java implementation **without the expected @Async boundary**.

**Do not overgeneralize that every final method on every proxy type is uninterceptable.** This override restriction belongs to **class-based proxies**. An interface-based proxy works differently, as analyzed in Section 5.

### A final Class Is Stricter Than a final Method

~~~java
public final class ClosedService {
    public String work() {
        return "ok";
    }
}
~~~

A subclass **cannot extend ClosedService**, so CGLIB cannot create a class proxy for this class. If the bean requires a class-based proxy, the application may fail proxy creation during startup; do not assume Spring will automatically turn a final class into a valid proxy.

If a **final class implements a business interface** and configuration allows it, a JDK dynamic proxy can still stand **in front of the interface** to intercept calls to the final class's instance. In that case, the bean is injected by the **interface**, not as a proxy object sharing the concrete class.

**A final field differs from a final method.** A `final` field prevents reassigning the reference after initialization (per Java rules); it does not prevent a **public non-final method** of the class from being intercepted by a subclass proxy. Having a `final` field in a bean **does not automatically break @Async**.

| Item Declared final | Effect |
| --- | --- |
| **final local variable** | Prevents reassigning the variable within its Java scope. |
| **final field** | Prevents reassigning the field under Java rules; does not lock nested mutable objects. |
| **final method** | Prevents overriding; **CGLIB cannot attach advice by overriding** that method. |
| **final class** | Prevents subclassing; **CGLIB cannot create a subclass proxy** of that class. |

When reviewing a class, check what `final` is applied **to**, rather than just searching for the string "final".

## 4. Modifier Limits: Direct Comparison of JDK and CGLIB

The lesson on the two proxy types compared their structure and injection behavior. Here the focus is on one narrow question: **which Java modifiers determine whether a method can be independently intercepted?**

| Condition on Target | JDK Interface Proxy | CGLIB Class-Based Proxy |
| --- | --- | --- |
| `private method` | No call path to a private method through the interface proxy. | Cannot be overridden to intercept. |
| `public final method` in interface | Can intercept **calls through the interface proxy** before delegating to the final implementation. | Cannot override a final method to apply advice. |
| `final class` implementing interface | JDK proxy can still sit in front of the interface if advisor/config matches. | Cannot subclass a final class. |
| Internal `this.publicAsync()` | Call bypasses proxy. | Call bypasses proxy. |

A JDK proxy handles calls through an `InvocationHandler` **before** delegating to the target, so a `final` implementation does not prevent interface interception. CGLIB needs subclassing/overriding, and therefore obeys `final` and `private`. This table describes **technical capability**, not a guarantee that Spring recognized the annotation or that the executor accepted the task; always verify proxy type, method signature, and actual call path. The next example proves the JDK Proxy boundary in plain Java.

## 5. Standalone Java 17 Example: A final Target Can Still Be Intercepted by a JDK Interface Proxy

This first example **does not use Spring**; it illustrates the **exact JDK dynamic proxy mechanism** to distinguish "final on target" from "call interception at the proxy." We count how many times the handler sees the `run` method. After calling `run` through the proxy, the counter increments. After calling `outer` through the proxy, the target calls `run` on itself via **this.run()**, and the counter does not increment further.

Save as **InterfaceProxyDemo.java**:

~~~java
import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.AtomicInteger;

public class InterfaceProxyDemo {
    public interface TaskPort {
        String run();
        String outer();
    }

    public static final class FinalTarget implements TaskPort {
        @Override
        public final String run() {
            return "work-done";
        }

        @Override
        public String outer() {
            return this.run();
        }
    }

    public static void main(String[] args) {
        FinalTarget target = new FinalTarget();
        AtomicInteger advisedRunCount = new AtomicInteger();

        TaskPort proxy = (TaskPort) Proxy.newProxyInstance(
                TaskPort.class.getClassLoader(),
                new Class<?>[] { TaskPort.class },
                (p, method, params) -> {
                    if (method.getName().equals("run")) {
                        advisedRunCount.incrementAndGet();
                    }
                    return method.invoke(target, params);
                }
        );

        System.out.println("Proxy.run result: " + proxy.run());
        System.out.println("Final method via interface intercepted: "
                + (advisedRunCount.get() == 1));

        System.out.println("Proxy.outer result: " + proxy.outer());
        System.out.println("this.run call intercepted: "
                + (advisedRunCount.get() == 2));
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 InterfaceProxyDemo.java
java InterfaceProxyDemo
~~~

**Program stdout:**

~~~text
Proxy.run result: work-done
Final method via interface intercepted: true
Proxy.outer result: work-done
this.run call intercepted: false
~~~

**Explanation:**

1. **FinalTarget** is a `final` class, and its **run()** is also `final`.
2. **proxy.run()** is a call through the **TaskPort** interface. The `InvocationHandler` runs, increments the counter, and then calls `target.run()`.
3. **proxy.outer()** also goes through the handler, yet the handler only increments the counter if the invoked method is named **run**. Once inside `target.outer()`, **this.run()** invokes `target.run()` directly **without re-entering the interface proxy**.
4. Hence the counter for `run` remains 1 after calling `outer`, making the final line `false`.
5. This is a **hand-written JDK Proxy** example; it does not prove that every Spring `@Async` configuration succeeds on final methods. To verify Spring, use a real Spring context and `@Async` as shown in the following sections.

**Observation:** a `final` class and `final` implementation do not inherently block a JDK interface proxy. What matters is whether the call passes through the proxy and whether advice is configured to handle that call.

## 6. Internal Calls (Self-Invocation): Even public Methods Can Lose Advice

Consider a service:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ExportService {
    public void startExport() {
        exportAsync(); // Equivalent to this.exportAsync().
    }

    @Async("exportExecutor")
    public void exportAsync() {
        // Heavy work.
    }
}
~~~

If another bean calls **startExport()** through the proxy, `startExport` can execute as a normal call. Inside it, **this.exportAsync()** does not go back out through the proxy for Spring to detect `@Async`. Consequently, **exportAsync can run synchronously right on the caller thread of startExport**.

This mistake easily occurs when developers think:

> "I put @Async on the method, so every call to the method runs asynchronously."

In reality, **@Async in proxy mode intercepts *the call path*, rather than turning the method body into an automatic multithreading construct**.

It is not only explicit `this` that triggers this bug. Both forms below are internal calls:

~~~java
this.exportAsync();
exportAsync();
~~~

If you directly invoke an instance created with **new ExportService()**, even from another bean, that instance is not managed by a Spring proxy; the annotation has no effect as it would when passing through a Spring bean proxy.

## 7. Safe Fix for Self-Invocation: Move the Call Site to Another Bean

The clearest and easiest-to-test approach is **splitting orchestration** and the **async worker** into two beans, with one bean injecting the other.

**ExportWorker.java** — public entry point:

~~~java
package example.demo;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ExportWorker {
    @Async("exportExecutor")
    public CompletableFuture<String> export(long orderId) {
        String result = "export-" + orderId;
        return CompletableFuture.completedFuture(result);
    }
}
~~~

**ExportFacade.java** — invokes via the Spring-injected bean:

~~~java
package example.demo;

import java.util.concurrent.CompletableFuture;
import org.springframework.stereotype.Service;

@Service
public class ExportFacade {
    private final ExportWorker worker;

    public ExportFacade(ExportWorker worker) {
        this.worker = worker;
    }

    public CompletableFuture<String> start(long orderId) {
        return worker.export(orderId);
    }
}
~~~

This code assumes **@EnableAsync**, an executor named **exportExecutor**, and Spring component scanning or appropriate bean registration. This is a **multi-file pattern for a Spring application**, not a standalone `javac` program.

Because **worker** is a Spring-supplied dependency, the caller uses a valid proxy object when the bean is created with async advice. Calling `worker.export(...)` passes through the proxy, allowing the interceptor to dispatch work to the executor. This is preferred over packing every method into one class and attempting to invoke a self-reference.

### Should You Inject Your Own Proxy?

Techniques exist for self-injecting the bean's own proxy or calling **AopContext.currentProxy()**, yet they create confusing coupling, risk circular dependencies, or require dedicated `exposeProxy` configuration. **Do not choose them as a first resort**. Separating a worker bean with clear responsibilities is usually simpler, easier to test, and less surprising.

## 8. Real Spring Example: Comparing public, private, final, and Self-Call

The following example uses **Spring Framework 6.2.x**, **Java 17**, and a **class-based proxy** explicitly requested via **@EnableAsync(proxyTargetClass = true)**. It uses methods returning **CompletableFuture<Boolean>**, checking whether the body actually executes on a thread different from the caller. To keep output deterministic, it does not print thread names that can vary.

Structure:

~~~text
async-proxy-demo/
├── pom.xml
└── src/main/java/example/ProxyAsyncDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>async-proxy-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

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
                <version>3.5.1</version>
                <configuration>
                    <mainClass>example.ProxyAsyncDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/example/ProxyAsyncDemo.java**:

~~~java
package example;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class ProxyAsyncDemo {
    @Configuration
    @EnableAsync(proxyTargetClass = true)
    public static class Config {
        @Bean("lessonExecutor")
        public ThreadPoolTaskExecutor lessonExecutor() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("lesson-");
            return executor;
        }

        @Bean
        public Worker worker() {
            return new Worker();
        }
    }

    public static class Worker {
        @Async("lessonExecutor")
        public CompletableFuture<Boolean> publicAsync(Thread caller) {
            return CompletableFuture.completedFuture(
                    Thread.currentThread() != caller);
        }

        public boolean selfCall(Thread caller) {
            return this.publicAsync(caller).join();
        }

        @Async("lessonExecutor")
        private CompletableFuture<Boolean> privateAsync(Thread caller) {
            return CompletableFuture.completedFuture(
                    Thread.currentThread() != caller);
        }

        public boolean callPrivate(Thread caller) {
            return privateAsync(caller).join();
        }

        @Async("lessonExecutor")
        public final CompletableFuture<Boolean> finalAsync(Thread caller) {
            return CompletableFuture.completedFuture(
                    Thread.currentThread() != caller);
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            Worker worker = context.getBean(Worker.class);
            Thread caller = Thread.currentThread();

            System.out.println("Public via proxy: "
                    + worker.publicAsync(caller)
                            .get(5, TimeUnit.SECONDS));
            System.out.println("Self-calling public: "
                    + worker.selfCall(caller));
            System.out.println("Calling private internally: "
                    + worker.callPrivate(caller));
            System.out.println("Calling final via CGLIB: "
                    + worker.finalAsync(caller).join());
        }
    }
}
~~~

Run from the directory containing **pom.xml** with JDK 17 and Maven:

~~~bash
mvn -q compile exec:java
~~~

**Expected application stdout** under the configuration above (excluding Maven/Spring log lines):

~~~text
Public via proxy: true
Self-calling public: false
Calling private internally: false
Calling final via CGLIB: false
~~~

**Detailed explanation of each line:**

1. **Public via proxy: true.** A caller outside the bean invokes `publicAsync` on the CGLIB proxy. The async interceptor submits the task to `lessonExecutor`; the body compares **Thread.currentThread()** with `caller` and sees they differ. **get(timeout)** waits for the result so output is deterministic.
2. **Self-calling public: false.** **selfCall** runs normally and then calls **this.publicAsync** on the target without going back through the proxy. The body runs right on the caller thread. The `CompletableFuture` value here is simply a `completedFuture` created directly; there is no `@Async` dispatch.
3. **Calling private internally: false.** **callPrivate** calls `privateAsync` directly, with no override/interception point. The body still runs on the thread calling `callPrivate`.
4. **Calling final via CGLIB: false.** Spring was forced to create a class-based proxy, yet CGLIB cannot override `finalAsync`. The call is not wrapped by the `@Async` interceptor; the thread comparison evaluates to `false`.
5. **Worker** is non-final so CGLIB can create a subclass proxy. The **final method** inside the class is what illustrates the limitation. A class-based proxy cannot overcome this restriction merely by adding an annotation.

This example **uses booleans and `get(timeout)`** rather than relying on scheduler timing, log order, or thread names. **proxyTargetClass**, executor name, and bean scope are all explicitly declared. If an environment uses a different AOP configuration or Spring version, inspect the actual proxy and adjust tests instead of treating this stdout as a guarantee for every environment.

**Important note on @Async:** the return type in the example is **CompletableFuture<Boolean>**. Under Spring's contract, an `@Async` method returning a result declares **Future/CompletableFuture**; inside the method body it can return **completedFuture** wrapping the computed result, while the interceptor provides the asynchronous boundary to the caller. Do not wrap it further with **supplyAsync** onto the common pool without a deliberate reason.

## 9. When Using an Interface-Based Proxy: A final Implementation Can Still Be Intercepted

Suppose a service exposes a **public interface**:

~~~java
package example.api;

import java.util.concurrent.CompletableFuture;

public interface TaskPort {
    CompletableFuture<String> perform(String id);
}
~~~

Implementation:

~~~java
package example.api;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public final class TaskPortImpl implements TaskPort {
    @Override
    @Async("taskExecutor")
    public final CompletableFuture<String> perform(String id) {
        return CompletableFuture.completedFuture("done:" + id);
    }
}
~~~

These are **two separate files in a Spring application**, not a complete Maven example. With a **JDK interface-based proxy** and an async advisor that detects the annotation, calling **taskPort.perform(id)** through the **TaskPort proxy** can be intercepted even though both the implementation class and method are `final`. Because a JDK proxy does not subclass **TaskPortImpl**.

To apply this safely:

- Inject the bean as **TaskPort**; do not require the proxy to be `TaskPortImpl`.
- Verify the application actually picks a **JDK dynamic proxy** rather than global configuration forcing CGLIB.
- Verify Spring detects the annotation given its placement and your Spring version.
- Write an integration test proving the **method actually runs on the executor**, not merely asserting that the annotation exists.
- If the application forces a class-based proxy on a **final TaskPortImpl**, proxy creation can fail. In that case, remove `final` from the class, change proxy strategy, or reorganize the interface/service.

The key point is **not to blindly "strip final from every method"** if the project follows other Java conventions. Determine the proxy type and API exposure first; nevertheless, for a new `@Async` worker, a **public non-final method on a non-final Spring-managed bean** remains the clearest, easiest, and lowest-risk choice.

## 10. Which Proxy Does Spring Choose? Runtime Inspection

In a Spring 6.x application, **@EnableAsync** defaults to **AdviceMode.PROXY**. The **proxyTargetClass** attribute lets you request a class-based proxy when using `PROXY` mode.

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync(proxyTargetClass = true)
public class AsyncConfiguration {
}
~~~

This is a **Spring configuration file**. Forcing class-based proxies can affect other beans needing AOP depending on global configuration mechanisms. Therefore, do not enable it casually just to work around one private/final method.

Some Spring Boot applications may activate class-based proxies via properties or other AOP configuration. When you need an exact answer, **inspect the actual proxy instance**:

~~~java
import org.springframework.aop.support.AopUtils;

Object bean = applicationContext.getBean("worker");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
~~~

This is an **illustrative snippet inside a method that has an `applicationContext` variable**; it requires Spring AOP on the classpath. The booleans reflect the bean's proxy type **at runtime**. Do not guess the proxy type from source class names or bean names.

Note that a **JDK proxy is not a subtype of the concrete target**. Code injecting the dependency by concrete class may fail, even though the interface-based proxy is completely valid for methods exposed on the interface.

### Call Path Check Table

| Case | Can Spring Proxy Advice Run? | Why |
| --- | --- | --- |
| Another bean calls a `public` non-`final` method via a class proxy | **Yes**, if advice matches | Proxy overrides the method to intercept |
| Another bean calls a `public` interface method via a JDK proxy | **Yes**, if advice matches | Call routes to the invocation handler |
| `private` method has `@Async`, internal caller invokes it | **No** | `private` cannot be intercepted through a proxy |
| `final` method via CGLIB | **No** | Cannot be overridden |
| `final` method on target called via JDK interface proxy | **Possible** | Interception happens at the interface proxy, no need to override final implementation |
| `final` class requested with CGLIB proxy | **No** | Cannot be subclassed |
| `final` class implementing an interface, suitable JDK proxy | **Possible** | JDK proxy implements the interface |
| Bean calls `this.publicAsync()` | **No** | Self-invocation bypasses the proxy |
| An instance created with `new` instead of a Spring bean | **No** | Instance does not pass through Spring's proxy |
| `public` `@Async` runs on worker and calls a `private` helper | Helper runs on worker, **but is not independently intercepted** | Worker context was already established at the public entry point |

The table describes **call interception capability**, not a guarantee that every call always runs asynchronously: that still depends on `@EnableAsync`, advisors, executors, saturation, rejection, injection style, and valid return types.

## 11. Remaining Issues: private/protected/package-private and Per-Annotation Rules

In Spring AOP, `private` and `final` are two very clear structural limits of class-based proxies. However, for other visibility levels, you should not apply a single rule across every annotation:

- For **@Async**, to keep lessons and production code predictable, a **public method** called by another bean through the proxy is the preferred pattern.
- Some other subsystems in Spring 6.x, such as **@Transactional** on class-based proxies, support **protected or package-private** methods under certain conditions; that **does not automatically prove @Async works the same way on all non-public methods**.
- A package-private method in a superclass from a different package may **not be visible to override** from the proxy subclass, effectively behaving like `private`.
- **Static methods** are likewise not overridden like ordinary instance methods; `@Async` is designed around instance calls through a Spring bean proxy. Do not treat a static method as a reliable `@Async` entry point.
- **Constructors** and **@PostConstruct** are not normal entry points for proxy-based `@Async`. If you need to start async work after beans are ready, use another bean to perform the appropriate call once lifecycle allows.

**Common mistake:** reading a guide specifically about `@Transactional`, and assuming `private`/`protected`/`final` behave identically for `@Async`. Distinguish **general** AOP limits from the **specific** contract and mechanics of each annotation.

### Kotlin and record Are Notable Cases

Kotlin classes and methods are **final** by default unless declared `open` or handled by a compiler plugin. If using Spring AOP class-based proxies, pay attention to how the compiler/plugin generates proxiable classes and methods. **Do not assume Spring annotations automatically make every Kotlin method open.**

In Java, a **record** is a **final class**. A `record` as an immutable DTO can be ideal for **passing data to a task**, yet it is not the right kind of bean if you need a CGLIB subclass proxy for an `@Async` entry point. Separating `record` DTOs from service beans with `public` non-`final` methods reduces friction.

## 12. Difference Between @Async and CompletableFuture.supplyAsync

An important question: "If a `private` or `final` method cannot be intercepted by `@Async`, is there still a way to run the task on another thread?"

Yes, but **that is not annotation interception**. A method can **explicitly submit a task to an `ExecutorService` or `CompletableFuture.supplyAsync`**, even if the enclosing method is `private`/`final`. Keep the two mechanisms distinct:

**Mechanism A — Spring proxy intercepts the call:**

~~~java
@Async("jobExecutor")
public CompletableFuture<String> runAsync() {
    return CompletableFuture.completedFuture("ok");
}
~~~

When called through a valid Spring proxy, the interceptor hands the work off to the executor.

**Mechanism B — self-submitting inside the method:**

~~~java
private CompletableFuture<String> createTask(
        java.util.concurrent.Executor executor) {
    return CompletableFuture.supplyAsync(
            () -> "ok",
            executor);
}
~~~

These are **two non-standalone illustrative snippets**, assuming the appropriate imports/context. In Mechanism B, the task can run on the executor **because code calls `supplyAsync`**; **there is no requirement to proxy the private method**.

Do not see a `CompletableFuture` returned and conclude `@Async` was applied. **CompletableFuture.completedFuture** can complete immediately on the caller. Conversely, `supplyAsync` can genuinely run on a worker **without any annotation**.

**Double-scheduling hazard:** if a `public` method was already dispatched to an executor by an `@Async` proxy, and inside its body it calls `supplyAsync` without specifying an executor or with a different executor, the task may unexpectedly jump to a second thread. That complicates context propagation, shutdown, transactions, error handling, and latency measurement. Add a second async layer only for a specific reason.

## 13. Beyond the Proxy: What Else Must Be Checked for @Async Correctness?

A call passing through the proxy does not guarantee the system processes the work successfully:

1. **Does the executor accept the task?** The pool might be saturated or shut down and throw **TaskRejectedException** at the submission boundary.
2. **Has the task started?** It might be waiting in a queue depending on `ThreadPoolTaskExecutor` settings.
3. **How are results/exceptions returned?** With `Future`/`CompletableFuture`, callers can observe success or failure. With `@Async void`, task errors do not automatically become exceptions in the caller.
4. **Is the caller blocking itself with `join()`/`get()`?** If it calls `get` immediately, the caller waits and loses the response-time benefit.
5. **Is input data safe to cross threads?** Mutable objects and request-scoped contexts can cause races or stale reads, even when the proxy works properly.
6. **Do `ThreadLocal`/`SecurityContext`/MDC/transactions need propagation?** Thread-bound contexts do not automatically appear correctly on the worker.
7. **Does the task have deadlines/cancellation and graceful shutdown?** Running asynchronously while holding workers indefinitely can still stall the system.

Do not work around proxy errors by making **every singleton field mutable** and reading them from background threads. That causes requests to interfere with one another. Pass business data via method parameters/immutable snapshots and manage executor bounds.

## 14. Exception: AspectJ Weaving Does Not Use the Same Proxy Model

Spring can use **AdviceMode.ASPECTJ** for async support with the right configuration and dependencies, instead of the default **AdviceMode.PROXY**. AspectJ uses **weaving** (compile-time or load-time) to attach advice at join points, without relying in the same way on a proxy wrapper standing in front of the target.

Key consequences:

- The **self-invocation bypasses proxy** limitation can be overcome with proper AspectJ weaving, because it no longer depends on calls passing through a proxy object.
- Simply changing **@EnableAsync(mode = AdviceMode.ASPECTJ)** in source code and rerunning **is not enough**. You need **spring-aspects** and proper weaving configuration; you must verify artifacts were woven and the advisor is actually active.
- The **proxyTargetClass** attribute is not the key when using `AdviceMode.ASPECTJ`, since JDK/CGLIB proxies as discussed above are not created.
- Do not automatically claim **every private/final method** is handled identically across all weaving setups; check join point types, AspectJ rules, versions, visibility, and integration tests.

In most Spring applications using standard `@Async`, **separating a public async service bean and calling through the proxy** is simpler and requires less infrastructure setup than adopting weaving.

## 15. Subtle Bug When Combining @Transactional and @Async

This scenario directly involves **call interception capability**, rather than being a deep dive into transactions:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.transaction.annotation.Transactional;

public class OrderService {
    public void create() {
        saveInTransaction(); // Self-invocation may bypass advice.
    }

    @Transactional
    public void saveInTransaction() {
        // If only called via this, the transaction proxy may not run.
    }

    @Async
    public void notifyAsync() {
        // If called via this.notifyAsync(), the async proxy may not run.
    }
}
~~~

This is an **illustrative snippet** assuming appropriate Spring configuration; not a complete service. Under proxy-based AOP, both `@Transactional` and `@Async` can be bypassed by self-invocation. Yet fixing it by splitting beans does not mean **the transaction automatically transfers from the request thread to the worker thread**. Transaction contexts are thread-bound and normally require the worker's own boundary.

Design example:

~~~text
OrderFacade (HTTP/request thread)
    |
    +-- orderService.save(...)       -> separate transaction
    |
    +-- notificationWorker.send(...) -> @Async via proxy
                                         -> worker logic / transaction if needed
~~~

If work must only be dispatched **after the transaction commits**, consider an appropriate **transactional event/outbox** mechanism. Calling `@Async` before commit can cause the worker to read uncommitted database state or hit wrong business ordering.

**Do not conflate concepts:** "`@Async` does not run because of final/private/self-call" is an **interception** error. "The worker lacks transaction/request context" is a **thread/context boundary** error. Both can occur together, yet they must be diagnosed and fixed separately.

## 16. Real Testing: Do Not Rely Only on Thread Names

In Spring AOP tests, verify at minimum:

- **The bean comes from `ApplicationContext`**, not a manually instantiated `new` object.
- **AopUtils.isAopProxy(bean)** confirms a proxy exists if configuration requires it.
- **AopUtils.isJdkDynamicProxy / isCglibProxy** identifies the type instead of guessing.
- The `@Async` call is made from **another bean** or from a runner holding the Spring-managed proxy.
- The task confirms **Thread.currentThread() differs from the caller** when proving dispatch to a worker.
- With `CompletableFuture`, use **get(timeout)** to avoid unbounded hanging tests.
- Write explicit tests for **private, final, and self-invocation** to document cases without interception.
- Test executor **rejection** and worker **exceptions**, without confusing them with proxy errors.

A test can accidentally pass even when `@Async` is broken:

~~~java
@Async
public CompletableFuture<String> method() {
    return CompletableFuture.completedFuture("ok");
}
~~~

If the test only asserts that `future.get()` returns `"ok"`, it still passes **when the method runs synchronously due to self-invocation**. You must verify **thread identity or dispatch signals**, such as using a `CountDownLatch` to pause the body and observing whether the caller returns before the body completes.

Do not rely on **Thread.sleep(100)** hoping the worker has started. Latches/barriers and timeouts make tests deterministic. Do not assert exact thread names or log ordering when the executor has multiple workers.

### Using CountDownLatch to Verify the Proxy Boundary

A test can:

1. Record the **caller Thread** before invoking the bean.
2. Prepare a public non-final worker method with **CountDownLatch started** and **CountDownLatch release**.
3. Call through the proxy, verifying the caller receives the `Future` before opening `release` while the executor is not saturated.
4. Then open `release` and wait on `future.get(timeout)`.
5. Record **Thread.currentThread()** inside the worker and assert it differs from the caller.
6. Repeat for a self-call from the target and compare, while **never using the single blocked caller thread itself to trigger `release`** since that would deadlock; use a separate test thread or proper barrier design.

With class-based proxies, testing a `public final` method must distinguish **not intercepted** from "ran so fast it looked synchronous." A very fast method can finish instantly even when properly dispatched. Checking thread identity as in the complete example is much stronger.

## 17. Step-by-Step Debugging When @Async Does Not Run on a Different Thread

Use a short investigative sequence in verifiable order:

**Step 1 — Verify the call origin.** Does code call a Spring-obtained bean (injected or `context.getBean`) or use **new**?

**Step 2 — Check whether Spring enabled async.** Is `@EnableAsync`, equivalent config, or the framework's async activation actually present?

**Step 3 — Inspect the annotated method.** Is the annotation placed on an appropriate **public entry point** or on a private helper/final method?

**Step 4 — Identify the proxy type.** Does `AopUtils` report JDK or CGLIB? Is a `final` class/method conflicting with subclass proxying?

**Step 5 — Trace the call path.** Does the caller invoke through the proxy from another bean or via **this.method()**? Does method A call method B in the same target expecting B to be intercepted?

**Step 6 — Inspect the executor.** Does the bean name in `@Async("...")` exist, have the right `Executor` type, stay running, and have capacity to accept tasks?

**Step 7 — Verify the outcome.** Measure thread identity inside the body, future completion, and exception paths. Do not judge solely by "the method returned too fast/slow."

**Step 8 — Separate other errors.** The worker might run on the right thread yet lose MDC, request context, security context, or transactions; that is a propagation/ownership issue, not the proxy itself.

**Step 9 — Add a CI test.** A small integration test verifying proxy type and thread boundary catches regressions from refactoring, adding `final`, changing interfaces, Boot configuration, or Spring upgrades.

## 18. Common Misconceptions

**"Putting @Async makes Java create a thread."** False. `@Async` requires Spring interception and an executor; the annotation does not transform Java bytecode into thread-creation instructions in proxy mode.

**"A private method with @Async runs in the background when called by a public method."** False. Private methods are not independently intercepted by the proxy. If the public method was dispatched by `@Async` first, the private helper may run **on the public method's worker**, which is a different matter.

**"A final method can never be intercepted by any proxy type."** False. CGLIB cannot override `final`; a JDK interface proxy can still intercept an **interface call** to a target whose method is `final`.

**"A final class can definitely never use AOP."** Inaccurate. CGLIB cannot subclass a `final` class, yet a JDK interface proxy can wrap a `final` implementation implementing an interface.

**"Having an interface guarantees Spring uses a JDK proxy."** Cannot be assumed. Spring Boot or global configuration may force class-based proxies; check at runtime.

**"@Async on a public non-final method always runs on a different thread."** Not guaranteed. Self-invocation, calling a `new` instance, missing `@EnableAsync`, rejection, executor configuration, and caller-runs policies all affect it.

**"this.async() still goes through the proxy because `this` is a Spring bean."** False in proxy-based AOP: direct internal calls on the target do not go through the proxy wrapper.

**"Calling a proxy method and immediately calling future.join() is still completely non-blocking."** False. `join()` can block the caller until completion.

**"A private helper running on a worker means @Async on the helper was intercepted."** False. It was invoked by the body of a public method that had already been dispatched.

**"Enabling proxyTargetClass=true fixes private/final."** False. That is the subclass model, which enforces override restrictions even more strictly rather than bypassing `private`/`final`.

**"@Transactional and @Async share the exact same visibility rules in every version."** False. Distinguish each annotation/subsystem, especially for `protected`/`package-private`.

**"Switching AdviceMode to ASPECTJ is enough."** False. It requires dependencies, actual weaving, and verification tests.

**"A Future returning the expected value means it ran asynchronously."** False. A `completedFuture` created directly on the caller returns the exact same result.

## 19. Reasoning Exercises

**Question 1.** A method has `@Async` and is declared `private`; a `public` method in the same class calls it. In proxy mode, does Spring intercept the private method?

**Answer:** No. There is no proxy entry point capable of intercepting a private method. It runs on the public caller's thread unless the public caller itself was moved to another thread by another mechanism.

**Question 2.** A `public` `@Async` method is non-final, yet it is called via `this.method()` from the same bean. Will it definitely run on the executor?

**Answer:** No. Self-invocation bypasses the proxy in `AdviceMode.PROXY`. Move the call site to another bean using the Spring-managed proxy.

**Question 3.** A `public final` method is on a bean wrapped in a class-based proxy. Can CGLIB override the method to advise it?

**Answer:** No. `final` forbids overriding. Restructure the code or use a different mechanism to satisfy the requirement.

**Question 4.** A `final` class implements `TaskPort`, and `perform()` is `final`. Can a JDK dynamic proxy intercept `TaskPort.perform()` calls?

**Answer:** Potentially yes. A JDK proxy implements the interface and intercepts the call before delegating to the target; it does not need to subclass the `final` class. You must ensure the Spring advisor matches and the app genuinely uses an interface proxy.

**Question 5.** A bean has a field **private final TaskRepository repo**. Does that prevent a `public` non-final `@Async` method from being proxied?

**Answer:** No. A `final` field differs from a `final` method/class; field injection/data structure and method overridability are separate things.

**Question 6.** A `public` `@Async` method runs on a worker and internally calls `private validate()`. Does `validate` run on the worker?

**Answer:** Yes, because it is an internal call occurring **after** the public entry point was already dispatched. However, `validate` is not independently intercepted by Spring.

**Question 7.** A Spring Boot app is configured to use class-based proxies. Does the service having an interface prove a `final` method will be intercepted?

**Answer:** No. If runtime actually uses CGLIB, a `final` method still cannot be overridden. Inspect `AopUtils` or the bean's proxy type.

**Question 8.** In the Java 17 JDK Proxy example, why did `proxy.outer()` not increment the advice counter for `run()`?

**Answer:** The invocation handler sees **outer**, but `target.outer()` calls **this.run()** directly on the target. The `run` call never returns to the proxy.

**Question 9.** If you switch to `CompletableFuture.supplyAsync` inside a private method, can the task run asynchronously?

**Answer:** Yes, because **supplyAsync** submits to an executor itself. This is not the effect of `@Async` proxy interception on a private method.

**Question 10.** Is a test that only calls the method and compares `Future.get()` with an expected string enough to verify `@Async`?

**Answer:** No. It only verifies the output value. You must observe the call path, proxy, thread identity, or dispatch signals.

## 20. Pre-Release Checklist for Services Using @Async

- [ ] The async entry-point method is placed on a **Spring-managed bean**, not a `new` instance.
- [ ] Async support is enabled in the right `ApplicationContext`.
- [ ] Calls to the async method **pass through the proxy**; self-invocation is avoided.
- [ ] With class-based proxies, the **bean class is non-final** and **methods to intercept are not private/final**.
- [ ] If using a JDK proxy, inject via the **interface** and confirm the method is exposed on the interface.
- [ ] `final` fields are not confused with `final` methods.
- [ ] Proxy type is verified with **AopUtils** rather than guessing defaults.
- [ ] Executor name is explicitly chosen, with capacity, rejection, and shutdown policies confirmed.
- [ ] `Future`/`CompletableFuture` is used for tasks needing results, handling exceptional completion.
- [ ] Inputs are properly captured before crossing thread boundaries; mutable singleton bean state is not shared across requests.
- [ ] Transaction/context propagation on the worker is checked if business logic requires it.
- [ ] Integration tests prove the method actually runs on an executor thread, not only asserting the return value.
- [ ] If using AspectJ weaving, dependencies, weaving configuration, and runtime results are verified.

## Conclusion

**Spring's call-interception capability depends on the *call path and proxy type*, not on merely having an annotation in source code.** In proxy-based `@Async` mode, `private` methods are not valid interception points, `final` methods cannot be overridden by CGLIB, `final` classes cannot be subclassed by CGLIB, and internal `this.method()` calls bypass the proxy even when the method is `public`. **JDK interface proxies have a distinct strength:** they can intercept calls through the interface even when the implementation class or method is `final`, provided Spring genuinely uses an interface proxy and advice recognizes the method.

The most maintainable design is usually a **public non-final @Async method on a non-final worker bean, called by another bean through a Spring-injected dependency**. Always verify runtime proxy type, which thread actually executes the body, executor overload behavior, and `Future` contracts to avoid "fake async"—methods that return the right result while actually running synchronously.

**References:** Spring Framework Reference — [Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html), [Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html); Javadocs for **@EnableAsync**, **@Async**, **AopUtils**, **ThreadPoolTaskExecutor**; Java 17 Javadocs for **java.lang.reflect.Proxy** and **java.lang.reflect.InvocationHandler**.
