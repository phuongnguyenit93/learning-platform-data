# Running Multiple Contexts in One JVM and Responsibility for Closing Each Context

A Java process can host **multiple Spring `ApplicationContext` instances simultaneously**. Each context manages its own set of bean definitions, bean instances, and lifecycle; all of them still run inside **the same JVM**. This capability is useful when you need to run two independent application parts, test multiple configurations in one process, or build a parent–child relationship between contexts. However, being able to create multiple contexts does not mean Spring automatically manages shutting down individual parts for the application: **whichever context is created must have an owner responsible for closing that context at the right time**.

In this lesson, "context" means **Spring `ApplicationContext`**, not HTTP servlet context, `SecurityContext`, or other context concepts.

## 1. One JVM, Multiple Spring Containers

Visualize two independent contexts in the same process:

```text
JVM / one Java process
|
+-- ApplicationContext A
|   +-- BeanFactory, bean definitions of A
|   +-- Singleton A, lifecycle callbacks of A
|   +-- Resources managed by A
|
+-- ApplicationContext B
    +-- BeanFactory, bean definitions of B
    +-- Singleton B, lifecycle callbacks of B
    +-- Resources managed by B

Both still share the JVM, classloader (typically),
static fields, system properties, and process-level resources.
```

This creates two distinct levels of scope:

- **Within one context**, `@Scope("singleton")` (the default for ordinary beans) means one bean instance per Spring container that owns that bean. The exact same bean definition can produce **two different instances** in two independent contexts.
- **Within the JVM**, `static` fields, classes loaded by a shared classloader, system properties, and certain global libraries/registries can be seen by both contexts. Spring does not automatically duplicate or reset these states merely because you create another context.

For example, two contexts can both define a bean named `paymentService` without conflict because they reside in two independent registries. Yet if both beans point to the same `static` cache, updating the cache in context A can still affect context B.

Do not confuse **multiple contexts** with **multiple JVMs**. Contexts inside one JVM still share memory and the fate of the process: calling `System.exit(...)` affects the entire process, not just one context.

## 2. Runnable Example: Two Independent Contexts

The example below targets **Java 17+ and Spring Boot 3.x**, with the `spring-boot-starter` dependency. We intentionally use `WebApplicationType.NONE` to focus on the Spring lifecycle, avoiding web server startup and HTTP port conflicts.

Create `src/main/java/com/example/multicontext/TwoContextsDemo.java`:

```java
package com.example.multicontext;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class TwoContextsDemo {

    private TwoContextsDemo() {
    }

    public static void main(String[] args) {
        ConfigurableApplicationContext first = open(args);

        try {
            ConfigurableApplicationContext second = open(args);

            try {
                ManagedResource bean1 =
                        first.getBean(ManagedResource.class);
                ManagedResource bean2 =
                        second.getBean(ManagedResource.class);

                System.out.println("Same bean? " + (bean1 == bean2));
                System.out.println(
                        "IDs: " + bean1.id() + ", " + bean2.id());

                // Close only the first context.
                first.close();

                System.out.println(
                        "Context 1 active: " + first.isActive());
                System.out.println(
                        "Context 2 active: " + second.isActive());
                System.out.println(
                        "Context 2 bean ID: "
                                + second.getBean(ManagedResource.class).id());
            } finally {
                // Even if the code above throws, still close context 2.
                second.close();
            }
        } finally {
            // If creating context 2 fails, context 1 is still closed.
            if (first.isActive()) {
                first.close();
            }
        }
    }

    private static ConfigurableApplicationContext open(String[] args) {
        return new SpringApplicationBuilder(DemoConfiguration.class)
                .web(WebApplicationType.NONE)
                .run(args);
    }

    @Configuration(proxyBeanMethods = false)
    public static class DemoConfiguration {

        @Bean(destroyMethod = "close")
        ManagedResource resource() {
            return new ManagedResource();
        }
    }

    public static final class ManagedResource implements AutoCloseable {

        private static final AtomicInteger NEXT_ID =
                new AtomicInteger();

        private final int id = NEXT_ID.incrementAndGet();

        int id() {
            return id;
        }

        @Override
        public void close() {
            System.out.println("Closing resource #" + id);
        }
    }
}
```

Run in a project directory configured with the Spring Boot Gradle plugin, with `TwoContextsDemo` as the main class:

```bash
./gradlew bootRun
```

On Windows, use `.\gradlew.bat bootRun`. If a Maven project is configured with the Spring Boot Maven plugin, you can run `./mvnw spring-boot:run` with the appropriate main class. This is Spring Boot application code; it cannot be compiled standalone with `javac TwoContextsDemo.java` without Spring libraries on the classpath.

Ignoring the banner and Spring Boot logs, **the lines printed by the example itself**, in order, will be:

```text
Same bean? false
IDs: 1, 2
Closing resource #1
Context 1 active: false
Context 2 active: true
Context 2 bean ID: 2
Closing resource #2
```

Why does this happen?

1. The first `open(args)` call creates context A, processes `DemoConfiguration`, and creates a `ManagedResource` with ID 1.
2. The second `open(args)` call creates a **new context**, processes the same configuration class, and creates a different `ManagedResource` with ID 2. Hence `bean1 == bean2` evaluates to `false`.
3. `first.close()` closes context A, triggering the destroy callback of the bean owned by A, which prints `Closing resource #1`.
4. Context B remains active and can still retrieve bean ID 2.
5. The inner `finally` block closes context B, which prints `Closing resource #2`. The outer `finally` block only closes A if A is still active.

The `NEXT_ID` field is `static`, so both contexts see **the same JVM-wide counter**. The counter uses `AtomicInteger` to be thread-safe if multiple threads instantiate objects concurrently. This is an intentional illustration showing that bean instances are isolated per context while `static` state is not.

Also note: `DemoConfiguration` only declares `@Configuration` and `@Bean`. It does not need `@SpringBootApplication` to demonstrate running a Spring context via `SpringApplicationBuilder`. In a typical Boot application, the root class can use `@SpringBootApplication` to also enable component scanning and auto-configuration.

## 3. What Does `close()` Actually Close?

The object returned by `SpringApplicationBuilder.run(...)` or `SpringApplication.run(...)` is `ConfigurableApplicationContext`. This interface lets you close the context using `close()`:

```java
context.close();
```

In a normal close, Spring runs the context destruction sequence, including stopping lifecycle components under the container's management and executing destruction callbacks for singleton beans owned by the context. Common mechanisms include:

| Mechanism | Used For |
|---|---|
| `@PreDestroy` | Cleanup method on a managed bean; Spring Boot 3 uses the annotation from `jakarta.annotation`. |
| `DisposableBean.destroy()` | Destruction callback defined by Spring. |
| `@Bean(destroyMethod = "close")` | Invokes the specified close method on the object returned by the factory method. |
| Spring-inferred `close`/`shutdown` methods | Applies when the bean is declared appropriately and inference is not disabled. |
| `SmartLifecycle.stop()` | Stops a component with an operational lifecycle; whether stop runs before or during destruction depends on lifecycle phases. |

In the section 2 example, `@Bean(destroyMethod = "close")` causes Spring to call `ManagedResource.close()` when the corresponding context is closed. You do not need to manually call `bean1.close()` and then `first.close()`; doing so risks closing the same resource twice if the object does not support idempotent close.

Several limitations to understand clearly:

- A context only manages destruction of registered objects that have an appropriate lifecycle contract. **Threads created manually with `new Thread(...)`, connections opened manually outside beans, callbacks stored in global registries, or static resources** do not automatically vanish just because the context closed.
- Spring **does not by default track and destroy every prototype bean** after it has been created and handed to the caller. If a prototype owns resources, the caller or an additional management mechanism must reclaim them.
- Closing one context does not automatically call `close()` on another independent context. However, if two contexts share an external object or co-own a physical resource, closing one **can indirectly impact** the other.
- After a context closes, `isActive()` becomes `false`, and you must not continue retrieving beans or submitting work to destroyed beans. Java references to an old bean may still exist in memory, but that does not mean the bean's resources are still usable.

For example, a manually created `ExecutorService` not registered as a bean can keep threads alive after the context closes. For background resources, use Spring-managed components, declare cleanup callbacks, or explicitly invoke `shutdown()`/`close()` at the owning boundary.

## 4. Who Owns the Responsibility for Closing Each Context?

The pragmatic rule is: **the code that creates or orchestrates a context must clearly establish who has the authority to close it**. This prevents both resource leaks and multiple owners closing the same resource.

| Resource Type | Appropriate Owner | When Closing Context |
|---|---|---|
| Singleton bean created specifically in A | Context A | A runs that bean's destroy callback. |
| Singleton bean created specifically in B | Context B | Closing A does not destroy B. |
| Bean declared in parent and used by child | Parent context | Closing child is not a command to destroy parent's bean. |
| Embedded web server owned by a web context | That web context itself | Stopped according to the context's lifecycle. |
| Shared client or pool created **once** outside contexts | Explicitly designated owner | Do not let both A and B destroy the same object. |
| `static` cache/registry or system property | Process level or owning code | Not automatically reset by a single context's lifecycle. |
| Object created manually outside Spring | Code that created the object | Must be reclaimed at the right time. |

A dangerous example: two contexts both point to **a single real `DataSource` object** and both declare destroy authority over that object. When A closes, the shared connection pool shuts down; B remains active, yet database access can fail. This is not a bug in `ApplicationContext`: the problem is **one resource having two lifecycle owners**.

There are two common ways to handle this:

1. Create separate resources for each context if full isolation is required, accepting the memory and connection overhead.
2. Create shared resources in the parent or an external owning component; children only use them and do not close shared resources themselves.

When choosing to share, do not think only about passing a reference: decide **who initializes, who closes, when it closes, and what happens if another consumer is still using it**.

## 5. Closing Properly When Startup Errors Occur

The most important pattern is ensuring an already-created context is closed if a subsequent context throws an exception during startup. For example:

```java
ConfigurableApplicationContext a = null;
ConfigurableApplicationContext b = null;

try {
    a = open(args);
    b = open(args);

    // Use both a and b.
} finally {
    if (b != null) {
        b.close();
    }
    if (a != null) {
        a.close();
    }
}
```

This is an **illustrative snippet placed in a class that has an `open(args)` method** like the section 2 example, not a standalone Java file. It closes in reverse creation order: B first, then A. Checking for `null` is critical in case the second `open(args)` call never returned a valid context.

When contexts are independent and do not need staggered early closing, you can use `try-with-resources` because `ConfigurableApplicationContext` supports `close()`:

```java
try (ConfigurableApplicationContext a = open(args);
     ConfigurableApplicationContext b = open(args)) {

    // Use both contexts within the try scope.
}
// Java closes b first, then closes a, even if the try body throws.
```

This pattern is also a snippet reusing `open(args)` from the previous example.

The difference between the two options: `try-with-resources` is concise when the lifespans of both contexts coincide; `try/finally` is more flexible when you need to close A earlier while continuing to use B.

If **the `run(...)` call itself** fails midway while creating a context, Spring Boot has mechanisms to handle startup failure and clean up the initializing context. Even so, that **does not relieve your responsibility to close other contexts that already started successfully earlier**.

## 6. How Do Two Independent Contexts Differ from a Parent–Child Relationship?

Not every pair of contexts has the same relationship.

### Two Independent Contexts

The section 2 example calls `open(args)` twice, creating A and B with no parent–child link:

```text
JVM
+-- A: BeanFactory A
+-- B: BeanFactory B
```

Normally, A does not automatically see beans registered by B; nor does B automatically see A's beans. To collaborate, the application must exchange data through an appropriate interface/channel or intentionally design shared resources.

### Parent–Child Context Hierarchy

Spring supports a context having a parent context:

```text
Parent context
  +-- CommonService (bean owned by Parent)
  |
  +-- Child context
        +-- FeatureService (bean owned by Child)
        +-- Can look up CommonService from Parent
```

In this relationship, the child can usually find parent beans if the child itself has no overriding bean matching the lookup name/scope. **The parent cannot automatically look down into beans that exist only in the child.** Both contexts still have their own lifecycles, though the child may depend directly on beans managed by the parent.

Spring Boot provides `SpringApplicationBuilder` to create hierarchies. The following snippet illustrates launching one, with `ParentConfig` and `ChildConfig` being **two `@Configuration` classes you must define for your application**:

```java
SpringApplicationBuilder parentBuilder =
        new SpringApplicationBuilder(ParentConfig.class)
                .web(WebApplicationType.NONE);

ConfigurableApplicationContext child = parentBuilder
        .child(ChildConfig.class)
        .web(WebApplicationType.NONE)
        .run(args);

ConfigurableApplicationContext parent =
        (ConfigurableApplicationContext) child.getParent();

try {
    // Child beans can use beans declared in parent.
} finally {
    try {
        child.close();
    } finally {
        parent.close();
    }
}
```

The cast above relies on the specific fact that **the parent was also created by Spring Boot's builder** and is a `ConfigurableApplicationContext`. Do not cast arbitrarily like this on an arbitrary `ApplicationContext`.

Points to remember about hierarchical lifecycles:

- **Closing child first, then parent** is the safe choice when the child needs parent beans to operate or clean up.
- `child.close()` is not a command to `parent.close()`; do not implicitly assume a single close call automatically tears down any arbitrary hierarchy.
- Closing the parent while the child is still active can leave the child holding references to destroyed parent beans/resources.
- If multiple children share one parent, close the parent only after all dependent children have finished and been properly closed.
- A bean with the same name in the child can shadow a bean in the parent when looked up from the child. Structure configurations so you do not accidentally declare duplicates or form wrong injection expectations.

Besides bean visibility, there is also **event propagation**: events published by a child can propagate up to the parent, causing listeners in the parent to observe child activity. For listeners that should handle **only a specific context**, check the event's source context or design listener registration accordingly.

Another detail: building a hierarchy can cause `Environment` and certain builder settings to be passed/merged across the parent–child link. Do not assume hierarchical contexts always have completely isolated profiles and properties; design and verify the actual configuration.

## 7. Multiple Web Contexts: Avoiding HTTP Port Conflicts

In the console application in section 2, `WebApplicationType.NONE` kept both contexts from needing a web server. If both A and B are **web application contexts**, each context can start its own embedded HTTP server. When both attempt to bind the same address and port, the second context to start can fail because the port is already in use.

For example, if two Servlet applications both try to listen on `localhost:8080`, residing in the same JVM does not make port 8080 automatically shared.

When you genuinely need **two separate web servers**, configure non-conflicting ports, such as:

```java
new SpringApplicationBuilder(ApiOneApplication.class)
        .properties("server.port=8081")
        .run(args);

new SpringApplicationBuilder(ApiTwoApplication.class)
        .properties("server.port=8082")
        .run(args);
```

This is **illustrative code**, assuming `ApiOneApplication` and `ApiTwoApplication` are two valid Spring Boot web configurations. Properties passed via `properties(...)` are default properties and remain subject to precedence from other configuration sources; verify the **effective port** when the application runs.

In test environments, `server.port=0` can ask the server to choose an available ephemeral port. Still, when testing multiple contexts in one JVM, clearly track: which test uses which context, which server belongs to which context, and who calls `close()`.

One web context can be closed while another web context continues serving requests, provided they do not depend on stopped shared resources. "Context B is still active" only describes context status; actual readiness of HTTP endpoints and external dependencies requires separate verification.

## 8. Background Tasks, Runners, and Shutdown Hooks

Two contexts sharing a configuration class do not only create beans twice: they can also **execute startup work twice**.

For example, each context can run its own `CommandLineRunner` / `ApplicationRunner` beans; if scheduling is enabled, each context can register its own `@Scheduled` tasks. This can be useful when each context manages a distinct workload, but can also lead to duplicate execution, duplicate messages, or competing over the same queue if not cleanly designed.

Examples of risks when sharing storage or external services:

- Contexts A and B both run "initial data seeding" code against the same database.
- Both register cleanup schedulers on the same table.
- One context closes a shared client while the other context's runner still needs to call that client.

Many Spring Boot applications register a JVM shutdown hook to close the context when the JVM terminates normally. That mechanism is useful at process end, **but does not replace lifecycle orchestration if one context needs to stop early while the JVM and other contexts remain running**. If code needs to selectively stop a specific context, use `context.close()` and clarify resource ownership instead of calling `System.exit(...)`.

For thread pools, schedulers, consumers, and connection pools, you must account for **stopping new work acceptance**, **draining in-flight work**, and **reclaiming resources**. Default callbacks may not satisfy every business requirement; when needed, configure graceful shutdown and timeouts according to the framework/libraries in use.

## 9. Deciding Whether to Use Multiple Contexts

Multiple contexts solve the problem of **isolating Spring configuration scopes and lifecycles** inside one process. It makes sense when parts of an application genuinely need to be initialized, used, and closed independently.

Some scenarios:

| Requirement | Consideration |
|---|---|
| Run two sets of beans with different configurations in one process | Two independent contexts; make property and resource isolation explicit. |
| Multiple features need shared foundational services | Parent holds shared resources, children hold feature beans, with clear close order. |
| Test different startup configurations | Dedicated context per test case; always close after the test. |
| Simply want to organize code into features | Usually a single context with clean packages, modules, profiles, and bean configs is enough. |
| Need fault, resource, or security isolation between services | Multiple contexts in one JVM do not create process isolation boundaries; consider separate processes/services. |

Each context carries initialization and memory cost. Two independent contexts may create two connection pools, two scheduler sets, two caches, and two corresponding configuration graphs. Conversely, sharing these resources arbitrarily breaks lifecycle isolation. Choosing the model must rest on the real boundaries of data and resources.

## 10. Common Errors and How to Recognize Them

**Error 1 — "A singleton has only one instance across the entire JVM."**

False for ordinary Spring singletons. A singleton bean is created **once per container owning that bean**, not once per JVM. The section 2 example shows two independent contexts creating two `ManagedResource` instances.

**Error 2 — "Closing A automatically closes B because both use the same configuration class."**

False. Sharing a configuration class does not merge two contexts into one. Context B is only affected when there is an explicit dependency relationship or an actually shared resource.

**Error 3 — "You can close the parent first and children will remain safe."**

Not guaranteed. Children may use beans or clients owned by the parent. Stop children and dependent work first, then close the parent.

**Error 4 — "Running the same web application twice gives two servers on 8080."**

Two servers cannot bind the exact same address/port pair in the usual way. Configure distinct ports or use a single web context if that is the intended architecture.

**Error 5 — "`close()` handles every thread and object I `new`ed anywhere."**

No. Spring can only manage the lifecycle of components it owns or resources application code explicitly binds to lifecycle callbacks. Manually creating resources without a cleanup path is a common cause of leaks.

**Error 6 — "Letting the JVM exit is enough; no need to clean up individual contexts."**

If the JVM must keep running other contexts, waiting for process exit holds unused contexts and their resources longer than intended. Moreover, a shutdown hook is no substitute for a controlled, ordered shutdown sequence.

**Error 7 — "If two contexts are independent, all state is independent too."**

`static` fields, system properties, files, network ports, and external services can still be shared. Evaluate both Spring container scope **and** JVM/system scope.

## 11. Self-Checks When Debugging

When a real application holds multiple contexts, you can inspect each object with a debugger and statements like:

```java
System.out.println(contextA.isActive());
System.out.println(contextB.isActive());
System.out.println(contextA.getParent() == null);
System.out.println(contextA == contextB);
```

This is an illustrative check assuming you already hold `contextA` and `contextB` variables; it is not a standalone program. For two independent contexts, `contextA == contextB` must be `false`. For hierarchies, `getParent()` helps inspect the parent–child relationship.

When troubleshooting an incident, answer in sequence:

1. Which context created the bean or resource having the issue? Is the bean in parent or child?
2. Who holds references to that resource? Is the same object shared across multiple contexts?
3. Which contexts have called `close()`, and in what order? Are any runners, scheduled tasks, or consumers still running?
4. If web servers are present, which address and port is each context bound to?
5. When one context closes, does the other context remain active **and** still able to use its required resources?

**Mental model to keep:** One JVM can run multiple `ApplicationContext` instances; singleton beans and lifecycles belong to the **owning context**, whereas static state and process-level resources can be **shared**. To safely close individual contexts, explicitly manage references, resource ownership, and shutdown order — especially with parent–child hierarchies, web servers, and background work.
