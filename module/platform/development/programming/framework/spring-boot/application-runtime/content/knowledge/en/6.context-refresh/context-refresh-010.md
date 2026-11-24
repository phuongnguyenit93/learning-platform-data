# Designing Hierarchies with SpringApplicationBuilder.parent, child, and sibling

A Spring Boot application does not necessarily have only one `ApplicationContext`. With `SpringApplicationBuilder`, we can compose contexts into a **parent–child tree**, or create **peer contexts (siblings)** sharing the same parent. Each context has its own bean registry and lifecycle, while a child can look up beans owned by the parent. This is a way to organize shared components alongside components that must be initialized, operated, or stopped independently within the same JVM.

This lesson focuses on the **exact semantics of the three APIs `parent(...)`, `child(...)`, and `sibling(...)`**, how to obtain references to each context, bean lookup direction, how startup arguments are passed, managing `Environment`, and closing contexts in a safe order. Examples run on Java 17+ and Spring Boot 3.3.x.

## 1. View a Context Hierarchy as a Tree, Not a Flat Bean List

Suppose an application has shared components (foundational configuration, clients, core services) and two functional groups that need to run independently:

~~~text
                         JVM (single process)
                               |
                     Parent ApplicationContext
                     + CommonService
                     + SharedCounter
                               |
                 +-------------+--------------+
                 |                            |
        Child A ApplicationContext    Child B ApplicationContext
        + AlphaTask                   + BetaTask
        + Beans private to A          + Beans private to B
                 |                            |
            looks up Parent              looks up Parent
            does not look up B           does not look up A
~~~

Here:

- **Parent** owns the shared beans. When A or B needs a bean not found in its own container, lookup can travel up to the parent.
- **Child A** and **Child B** own their private beans. They do not automatically see beans that exist only in the other sibling.
- **Parent does not automatically look down into children** to find beans; normal lookup goes from child up to parent.
- **Each context has its own lifecycle**. Closing A does not automatically close B or the parent; however, shared resources and events can cause contexts to affect each other indirectly.

This is still **one JVM**: contexts can share the classloader, static fields, files, network ports, and external services. A Spring hierarchy does not create process-level isolation boundaries.

A `singleton` bean is a singleton **within the container that owns that bean**. If the parent creates `SharedCounter`, A and B can look up **the exact same instance** from the parent. However, if A and B each declare their own `SharedCounter` bean, those are two separate instances and can shadow the parent bean during lookups by name or type.

## 2. What Does `SpringApplicationBuilder` Solve?

`SpringApplicationBuilder` resides in package `org.springframework.boot.builder`. It is a fluent API for configuring `SpringApplication` and supports building relationships across multiple `ApplicationContext` instances.

| API | Action | Builder returned | Common pitfall |
|---|---|---|---|
| `parent(Class<?>... sources)` | Adds an application as parent of the current builder. | **The newly created/assigned parent builder**. | If you call `run()` immediately on the result of `parent(...)`, you are running the parent builder. |
| `parent(ConfigurableApplicationContext parent)` | Attaches an already-running parent context to the current builder. | **The current builder**. | Parent already exists; you must manage the parent's lifetime. |
| `child(Class<?>... sources)` | Creates a child application of the current builder. | **The new child builder**. | Configuration and bean definitions are not all automatically copied; this is a separate context. |
| `sibling(Class<?>... sources)` | Creates a builder for another context sharing the same parent. | **The new sibling builder**. | Has a side effect: may start the current application and parent **without args** if not yet running. |
| `sibling(Class<?>[] sources, String... args)` | Creates a sibling while passing arguments for starting the current application and parent if not yet running. | **The new sibling builder**. | The `args` on this overload serve the eagerly triggered startup; the new sibling itself still needs `run(args)`. |
| `run(String... args)` | Runs the current application; if a configured parent is not running yet, the parent runs first. | **ConfigurableApplicationContext** of the current builder. | Returns the context at the node you called it on, not the entire tree. |
| `context()` | Retrieves the context started by this builder. | The context, or `null` if not yet started. | Useful when `sibling(...)` started another builder as a side effect. |

Two common simple invocations:

~~~java
ConfigurableApplicationContext child =
        new SpringApplicationBuilder(ParentConfig.class)
                .child(ChildConfig.class)
                .run(args);
~~~

And:

~~~java
SpringApplicationBuilder childBuilder =
        new SpringApplicationBuilder(ChildConfig.class);

childBuilder.parent(ParentConfig.class); // Do not chain run on parent()'s return value
ConfigurableApplicationContext child = childBuilder.run(args);
~~~

These snippets **illustrate the API**, assuming `ParentConfig`/`ChildConfig` are two valid Spring configuration classes and imports are present. Both approaches intentionally launch **the child** (the parent is launched beforehand if needed).

An easy mistake to make is:

~~~java
new SpringApplicationBuilder(ChildConfig.class)
        .parent(ParentConfig.class)
        .run(args);
~~~

Calling `parent(Class...)` **returns the parent builder**, so the chain above does not behave like "run child." To control precisely which builder is `run`, keep the child's reference first as shown above, or start from the parent and call `child(...).run(args)`.

## 3. Using `child(...)`: Root First, Child Branch Next

This is the easiest structure to follow:

~~~java
SpringApplicationBuilder rootBuilder =
        new SpringApplicationBuilder(ParentConfig.class)
                .web(WebApplicationType.NONE);

SpringApplicationBuilder childBuilder =
        rootBuilder.child(ChildConfig.class)
                .web(WebApplicationType.NONE);

ConfigurableApplicationContext child = childBuilder.run(args);
ConfigurableApplicationContext parent = rootBuilder.context();
~~~

This snippet is part of a program requiring valid `ParentConfig` and `ChildConfig` classes. `WebApplicationType.NONE` avoids opening a web server so we can focus on BeanFactory and lifecycle behavior.

**What happens when `childBuilder.run(args)` runs?**

1. Boot recognizes that the child builder has a parent.
2. If the parent is not running yet, the parent is launched first with the arguments configured on its builder.
3. The child is attached to the existing parent context.
4. The child is configured and refreshed from its own sources.
5. `run(...)` returns **the child context**; `rootBuilder.context()` is how you separately obtain the parent context.

If a bean type is declared only in the parent, the child can retrieve it via `child.getBean(Type.class)` through hierarchical lookup. If the child has a definition with the same name, the child's definition can shadow the parent's bean during lookup; however, injection by type still considers candidate counts and qualifiers, so do not assume every type collision resolves automatically.

Do not view `child(...)` as cloning the parent. Parent and child are **two containers** with a lookup relationship, not a single container with two names.

## 4. Using `parent(...)`: Watch the Returned Builder

There are two groups of scenarios.

### Creating a Parent from Configuration Classes

When you already have a child builder:

~~~java
SpringApplicationBuilder childBuilder =
        new SpringApplicationBuilder(ChildConfig.class)
                .web(WebApplicationType.NONE);

SpringApplicationBuilder parentBuilder =
        childBuilder.parent(ParentConfig.class)
                .web(WebApplicationType.NONE);

ConfigurableApplicationContext child = childBuilder.run(args);
ConfigurableApplicationContext parent = parentBuilder.context();
~~~

`parent(Class<?>... sources)` adds a parent above the child. Because it **returns the parent builder**, the `.web(NONE)` call in the assignment above applies to the parent; the child already received its own `web(NONE)`. Keeping both variables makes the code easy to follow and easy to close in order.

### Using an Already-Running Parent

If the parent was built earlier on a separate lifecycle:

~~~java
ConfigurableApplicationContext parent =
        new SpringApplicationBuilder(ParentConfig.class)
                .web(WebApplicationType.NONE)
                .run(args);

ConfigurableApplicationContext child =
        new SpringApplicationBuilder(ChildConfig.class)
                .web(WebApplicationType.NONE)
                .parent(parent)
                .run(args);
~~~

In the overload accepting a `ConfigurableApplicationContext`, `parent(parent)` **returns the current builder**, because it attaches an already-running context. This is an illustrative snippet; real code needs `try/finally` to close the child before the parent if one of the steps fails.

The benefit of this form is sharing a parent already created and maintained by other code. In return, you must define **who owns the parent** very clearly: the child only "borrows" beans/resources from the parent and must not unilaterally decide when the parent shuts down while other children still use it.

## 5. Using `sibling(...)`: Two Branches Sharing One Parent

A sibling is not a "child of the current child." It is **another child of the same parent**.

~~~text
parentBuilder
    |
    +-- alphaBuilder  ----- sibling(...) -----> betaBuilder
    |         |                              |
    |     Child A                          Child B
    +----------- same Parent context --------+
~~~

Suppose we already have:

~~~java
SpringApplicationBuilder parentBuilder =
        new SpringApplicationBuilder(ParentConfig.class)
                .web(WebApplicationType.NONE);

SpringApplicationBuilder alphaBuilder =
        parentBuilder.child(AlphaConfig.class)
                .web(WebApplicationType.NONE);
~~~

You can create a sibling as follows:

~~~java
SpringApplicationBuilder betaBuilder =
        alphaBuilder.sibling(new Class<?>[] {BetaConfig.class}, args)
                .web(WebApplicationType.NONE);

ConfigurableApplicationContext beta = betaBuilder.run(args);
ConfigurableApplicationContext alpha = alphaBuilder.context();
ConfigurableApplicationContext parent = parentBuilder.context();
~~~

With the `sibling(new Class<?>[]{...}, args)` overload, **calling `sibling(...)` may already start the parent and alpha** if they are not active yet. Consequently `alphaBuilder.context()` can retrieve the context without calling `alphaBuilder.run(args)` separately. Calling `betaBuilder.run(args)` is the step that starts beta.

**Why store all three builders?** Because each builder holds a reference to a different context. If you only kept a variable pointing to `betaBuilder`, cleanup code could hardly know for certain which contexts were started as a side effect.

If you use the shorter overload:

~~~java
SpringApplicationBuilder betaBuilder = alphaBuilder.sibling(BetaConfig.class);
~~~

the API may start alpha and parent with **empty arguments** if they are not running yet. If the program needs `--spring.profiles.active=dev` or command-line config as soon as parent/alpha start, call the overload taking `args` or explicitly run the contexts before creating the sibling. Do not expect a later `betaBuilder.run(args)` call to retroactively alter contexts that have already started.

## 6. Complete Java Example: Parent and Two Siblings Sharing a Bean

The following example creates exactly **three contexts**: parent holds a shared counter; child A and child B each hold their own service. It verifies bean lookup direction and shows that closing A does not stop B or the parent.

Create file `src/main/java/com/example/hierarchy/HierarchyDemo.java`:

~~~java
package com.example.hierarchy;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class HierarchyDemo {

    private HierarchyDemo() {
    }

    public static void main(String[] args) {
        SpringApplicationBuilder parentBuilder =
                new SpringApplicationBuilder(ParentConfig.class)
                        .web(WebApplicationType.NONE);

        SpringApplicationBuilder alphaBuilder =
                parentBuilder.child(AlphaConfig.class)
                        .web(WebApplicationType.NONE);

        SpringApplicationBuilder betaBuilder = null;

        try {
            // sibling() may start parent and alpha.
            // Overload with args passes args to those eagerly started apps.
            betaBuilder = alphaBuilder
                    .sibling(new Class<?>[] {BetaConfig.class}, args)
                    .web(WebApplicationType.NONE);

            // Start beta, retrieve contexts already created by builders.
            ConfigurableApplicationContext beta =
                    betaBuilder.run(args);
            ConfigurableApplicationContext alpha =
                    alphaBuilder.context();
            ConfigurableApplicationContext parent =
                    parentBuilder.context();

            SharedCounter counterA = alpha.getBean(SharedCounter.class);
            SharedCounter counterB = beta.getBean(SharedCounter.class);

            System.out.println(
                    "A and B share parent: "
                            + (alpha.getParent() == beta.getParent()));
            System.out.println(
                    "Parent owns counter: "
                            + parent.containsLocalBean("sharedCounter"));
            System.out.println(
                    "A and B share counter: " + (counterA == counterB));
            System.out.println(
                    "B sees alphaTask: " + beta.containsBean("alphaTask"));

            System.out.println(
                    "Value from A: "
                            + alpha.getBean(AlphaTask.class).next());
            System.out.println(
                    "Value from B: "
                            + beta.getBean(BetaTask.class).next());

            // Close A while beta and parent remain alive.
            alpha.close();

            System.out.println("A active: " + alpha.isActive());
            System.out.println("B active: " + beta.isActive());
            System.out.println(
                    "Value from B after closing A: "
                            + beta.getBean(BetaTask.class).next());
        } finally {
            // Close in order: child beta -> child alpha -> parent.
            // Each finally still attempts to close the next context, even if
            // another close step throws an exception.
            try {
                closeIfActive(
                        betaBuilder == null ? null : betaBuilder.context());
            } finally {
                try {
                    closeIfActive(alphaBuilder.context());
                } finally {
                    closeIfActive(parentBuilder.context());
                }
            }
        }
    }

    private static void closeIfActive(
            ConfigurableApplicationContext context) {
        if (context != null && context.isActive()) {
            context.close();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class ParentConfig {

        @Bean(destroyMethod = "close")
        SharedCounter sharedCounter() {
            return new SharedCounter();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AlphaConfig {

        @Bean
        AlphaTask alphaTask(SharedCounter counter) {
            return new AlphaTask(counter);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class BetaConfig {

        @Bean
        BetaTask betaTask(SharedCounter counter) {
            return new BetaTask(counter);
        }
    }

    public static final class SharedCounter implements AutoCloseable {

        private final AtomicInteger value = new AtomicInteger();

        int next() {
            return value.incrementAndGet();
        }

        @Override
        public void close() {
            System.out.println("Parent counter closed");
        }
    }

    public static final class AlphaTask {

        private final SharedCounter counter;

        public AlphaTask(SharedCounter counter) {
            this.counter = counter;
        }

        int next() {
            return counter.next();
        }
    }

    public static final class BetaTask {

        private final SharedCounter counter;

        public BetaTask(SharedCounter counter) {
            this.counter = counter;
        }

        int next() {
            return counter.next();
        }
    }
}
~~~

This is a **complete Java file**; configuration classes are declared as `public static` nested classes to avoid creating multiple small files. The project needs the Spring Boot starter, but no HTTP server. We use explicit `@Configuration` classes as primary sources rather than `@SpringBootApplication` so component scanning does not accidentally pull all of A, B, and parent configurations into a single context.

If you need a standalone Gradle project, a minimal `build.gradle` for the example:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.hierarchy.HierarchyDemo'
}
~~~

Run from the project directory with the Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows use `.\gradlew.bat bootRun`. If you have not generated a wrapper, prepare Gradle and the Spring Boot project first; `javac HierarchyDemo.java` alone is insufficient because the code needs Spring Boot/Spring Framework on the classpath.

Ignoring the banner and extra logs printed by Spring Boot, **the lines printed by the program itself** appear in order:

~~~text
A and B share parent: true
Parent owns counter: true
A and B share counter: true
B sees alphaTask: false
Value from A: 1
Value from B: 2
A active: false
B active: true
Value from B after closing A: 3
Parent counter closed
~~~

Why do these results occur?

1. Parent creates exactly one `sharedCounter` bean. Neither A nor B defines this bean itself, so both retrieve it from the parent; the reference comparison yields `true`.
2. A creates `alphaTask`, and B creates `betaTask`. Looking up `alphaTask` from B fails because that bean exists only in sibling A.
3. Both services call `next()` on the parent's single `SharedCounter`, so the counter increments from 1 to 2 and then 3.
4. `alpha.close()` marks A inactive, while beta and parent remain active. B can still use the parent's counter.
5. The `finally` block closes B, skips A because A is already closed, and then closes the parent. Only when the parent closes does the destroy callback of `sharedCounter` print `Parent counter closed`.

In an actual run, logs from initializing multiple Spring applications may be interleaved between the lines above. Because `WebApplicationType.NONE` is used and a single main thread executes calls to the counter, the values 1, 2, 3 in this example are deterministic.

## 7. Bean Visibility: One-Way Visibility and Child Shadowing

A context tree can be visualized by its lookup rules:

~~~text
Child A: look up bean in A -> if absent, look up in Parent
Child B: look up bean in B -> if absent, look up in Parent
Parent:  look up bean in Parent; does not search A/B
Child A: does not automatically search beans existing only in Child B
~~~

The table below helps distinguish common questions:

| Question | Typical outcome |
|---|---|
| Can A retrieve `SharedCounter` registered only in the parent? | Yes, via the ancestor bean factory. |
| Does B receive that exact same instance? | Yes, if B uses the parent bean and does not declare its own. |
| Can B automatically retrieve `AlphaTask` registered only in A? | No. |
| Can the parent automatically retrieve `BetaTask` registered only in B? | No. |
| What if A defines a bean with the same name as one in the parent? | The bean in A can shadow the same-named parent bean for lookups from A. |
| If two children both have a bean named `client`, is there a name collision? | Not merely for having the same name; the two bean registries are independent. |
| Does a singleton bean exist exactly once across the whole JVM? | No. Regular singletons belong to the owning container; only sharing a parent bean yields one instance shared across children. |

Methods to help inspect:

~~~java
alpha.containsLocalBean("sharedCounter"); // false
alpha.containsBean("sharedCounter");      // true
parent.containsLocalBean("sharedCounter");// true
beta.containsBean("alphaTask");          // false
~~~

This is an illustrative snippet in the context of the example above. `containsLocalBean` checks that container alone; `containsBean` can include beans from ancestors.

**Configuration warning:** If the parent has an overly broad `@ComponentScan`, the parent may end up creating beans intended strictly for children. If a child also scans the parent's entire package, some beans may be created twice. Therefore, when designing a hierarchy, select package boundaries and `@Configuration` classes deliberately. Putting `@SpringBootApplication` on all three contexts with the same root package easily creates confusing duplicate configurations.

## 8. `Environment`, Profiles, and Arguments Are Not Completely Independent

Even though each context has its own bean registry, the builder mechanism can **copy or share environment settings** across nodes. Per the `SpringApplicationBuilder` API, when creating a child, default arguments and environment are passed downward according to builder semantics; when adding a parent, relevant settings can propagate upward. Boot also has specific rules when configuring profiles/property sources in a hierarchy.

Therefore:

- Do not assume A and B have completely isolated sets of profiles or `application.properties` merely because they are two contexts.
- Calling `profiles("dev")` on a builder must be evaluated across **the entire hierarchy**, because this method can affect parent/children. Check `Environment.getActiveProfiles()` on each context after running.
- A property with the same name can appear in multiple property sources. Configuration precedence must be checked according to how Boot actually processes it, especially when combining command-line arguments and defaults.
- Use the `sibling(Class[], args)` overload if the parent/first child needs `args` right when creating the sibling triggers their startup.
- With `parent(ConfigurableApplicationContext)`, the parent already has its own `Environment` and lifecycle; the child must not be assumed to alter configuration already applied to the parent earlier.

Illustrative example showing how to inspect the environment:

~~~java
System.out.println(
        java.util.Arrays.toString(
                parent.getEnvironment().getActiveProfiles()));
System.out.println(
        java.util.Arrays.toString(
                alpha.getEnvironment().getActiveProfiles()));
System.out.println(
        java.util.Arrays.toString(
                beta.getEnvironment().getActiveProfiles()));
~~~

This snippet uses variables from the section 6 example. Do not assume profile arrays are identical or distinct before explicitly defining config sources and verifying each context.

If business requirements demand strict configuration isolation, separate JVMs or separate OS processes may be more appropriate than a Spring hierarchy.

## 9. When the Hierarchy Includes a Web Server

Spring Boot automatically determines `WebApplicationType` from the classpath if you do not set it explicitly. When building a hierarchy containing Spring MVC or WebFlux, Boot documentation recommends **placing web components in child contexts**, while the parent provides shared services/configuration.

For example, architecturally:

~~~text
Parent (NONE)
 +-- Shared DataSource / Services
 |
 +-- Child API A (SERVLET, server.port=8081)
 +-- Child API B (SERVLET, server.port=8082)
~~~

This is only a **deployment diagram**, not a complete runnable configuration. When multiple web children actually start their own embedded servers, ensure they do not bind the same host and port. If two children both try to open 8080, one child may fail because the port is already in use.

Additional considerations:

- The parent should focus on beans independent of servlet context/request scope; place controllers, servlet filters, and web configuration in the corresponding child.
- Each web child can start its own embedded server. Closing one child can stop that child's server while siblings keep running.
- If multiple children share one `DataSource`, the parent's pool stays open until the parent closes. Do not close the pool before all children have stopped using it.
- Do not assume calling `.properties("server.port=8081")` on a builder always overrides command-line arguments: it sets a default property, so verify which value takes effect.
- Running multiple web contexts in a single JVM carries runtime cost and operational complexity; typically use it only when clear lifecycle or bean-isolation requirements exist.

If you merely want to organize logic into multiple API functional areas, **a single context with separate packages or code modules** is usually simpler to operate.

## 10. Lifecycle: Parent Starts First, Parent Closes Last

In a hierarchy created and run via builders, the natural dependency relationship is:

~~~text
START:
  Parent -> Child A -> Child B
  (A may be auto-started by sibling() before B.run())

STOP:
  Child B -> Child A -> Parent
~~~

This is **an intentionally designed order**, not a promise that Spring will automatically close every node in the tree in one sweep when you close any single node.

Why should the parent close last? Children may be using parent-owned beans such as connection pools, schedulers, caches, or authentication services. Closing the parent early leaves references held by children pointing to already-shut-down resources, even though `child.isActive()` still returns `true`.

Cases to distinguish:

- **Closing A:** A destroys singletons owned by A; B and parent are not automatically closed.
- **Closing parent:** parent destroys beans owned by parent. Still-open children may stay alive yet fail because shared dependencies were destroyed.
- **Closing B after A:** B runs its own lifecycle cleanup independently; beans originating from the parent must not be destroyed by B as private resources.
- **Same resource registered for destruction in multiple contexts:** risks double-closing or one context breaking a resource another context still uses.

The example in section 6 puts `@Bean(destroyMethod="close")` **only in the parent**. A and B only hold references, without registering additional destruction ownership on the same object. This is critical when sharing connection pools, executors, or file handles.

For background tasks, before closing the parent, stop accepting new work, drain or cancel in-flight work per application policy, and then close dependent contexts. If the parent holds an `ExecutorService` while workers in B still submit tasks, closing the parent first can trigger `RejectedExecutionException` or lost work.

### Using `try/finally` with Multiple Nodes

Creating a sibling has side effects, so code calling `sibling(...)` should also sit **inside the cleanup region**. The example in section 6 achieves this by creating the parent builder and alpha builder, then wrapping both `sibling(...)` and `run(...)` inside `try/finally`. If launching B fails, the already-started parent and A contexts are still handled for closing.

For more complex hierarchies, you can maintain a list of successfully initialized nodes and close them in reverse dependency order, logging any cleanup exceptions. Avoid calling `System.exit(...)` to stop a single child, as that affects the entire JVM.

## 11. Spring Events Can Propagate from Child to Parent

Spring supports propagating certain `ApplicationEvent`s from children up to ancestors. As a consequence, a listener registered in the parent can observe both the parent's events **and** events bubbling up from children.

For instance, with lifecycle/context events, a parent listener may receive multiple events of the same type coming from different contexts. If handled without distinguishing the source, you can log duplicates, miscount startups, or run cleanup accidentally.

For listeners receiving `ApplicationContextEvent` (such as `ContextRefreshedEvent`), you can check:

~~~java
if (event.getApplicationContext() == ownContext) {
    // Only handle events originating from this listener's context.
}
~~~

This is an illustrative logic snippet: `event` and `ownContext` must be provided in an actual listener. For Spring Boot startup events that expose the context, use the event's context-accessor API and compare against the managed context.

**Do not treat every event as a signal that an independent node restarted.** An event bubbling up from a child to the parent can trigger a parent listener an extra time. This is a notable difference when comparing a hierarchy against two completely unrelated contexts.

## 12. Runners, Bean Lifecycle, and Startup Conditions

When `SpringApplicationBuilder` launches a node, that node runs `SpringApplication.run(...)`, refreshes, invokes startup runners, and publishes corresponding events. With multiple nodes, this process can occur multiple times.

The section 6 example omits `CommandLineRunner` to keep output easy to verify. In real applications:

- A runner declared in a given context has a lifecycle relationship with that context; do not assume every runner executes only once across the entire JVM.
- `@Scheduled` beans or message consumers registered in multiple children can run concurrently or duplicate work against the same queue/data store.
- A context failing to launch after `sibling(...)` has already started the parent and prior child does not mean every context rolls back together automatically; orchestration code must clean up already-running nodes.
- Beans depending on the parent can be created inside a child before the child is ready; the parent having refreshed does not prove the child is ready.

When readiness is needed per web child, check the status of that specific child rather than watching only the parent's `ApplicationReadyEvent`. Even with a shared datasource or message bus, the parent's health alone is insufficient to guarantee every child is ready for traffic.

## 13. When Should You Choose Parent–Child–Sibling?

| Need | Reasonable choice |
|---|---|
| Share a core set of beans while multiple feature groups have separate lifecycles | Parent holds shared beans; each group is a child. |
| Two independent modules sharing foundational services without seeing each other's private beans | Two siblings sharing one parent. |
| Attach a new context to an already-running foundational context | `parent(ConfigurableApplicationContext)`. |
| Simply organize controllers/services in one web application | A single context is usually simpler. |
| Each group requires independent CPU/memory, permissions, or fault isolation | Separate processes/services; an in-JVM hierarchy provides no process isolation. |
| Want to test multiple configuration sets within one process | Separate contexts, minding environment and shared resources. |

A parent–child organization is only valuable when bean and lifecycle boundaries carry real operational meaning. Never create a context tree merely to replace package organization or regular dependency injection.

## 14. Design Checklist and Common Mistakes

**Mistake 1 — Calling `parent(...).run(args)` and thinking you are running the child.**

Remember that the overload taking class sources returns **the parent builder**. Keep the child builder separately or start from the parent and call `child(...).run(args)`.

**Mistake 2 — Assuming `sibling(...)` does nothing before `run()`.**

The API has a side effect: it can launch the current application and parent. Choose the overload accepting `args` when early startup arguments are needed; manage cleanup even if `sibling(...)` throws an exception.

**Mistake 3 — Expecting sibling A to automatically retrieve sibling B's private beans.**

Normal lookup only travels up to ancestors. Move genuinely shared beans to the parent or design an explicit communication interface; never rely on implicit sibling lookup.

**Mistake 4 — Scanning the same broad package in both parent and child.**

This can produce duplicate beans, duplicate listeners, duplicate schedulers, or break configuration boundaries. Scope source classes, base scan packages, and auto-configuration precisely.

**Mistake 5 — Closing the parent before children finish.**

Children may remain active while shared dependencies are already destroyed. Typically close children first and then the parent; if background work exists, stop and await completion per business contract.

**Mistake 6 — Assuming environment/profiles of nodes are completely isolated.**

Builders share/coordinate environment and default arguments. Print or inspect properties and active profiles in each context to verify.

**Mistake 7 — Starting both web children on the same port.**

Each embedded server needs a valid host/port; separate ports or change the architecture. Multiple contexts do not make an HTTP port automatically shareable.

**Mistake 8 — Parent listener treating a child event as the parent's own.**

Check the event's source context and filter for the target node. Some application events propagate upward to ancestors.

### References

- Spring Boot 3.3, `SpringApplicationBuilder` Javadoc: https://docs.spring.io/spring-boot/docs/3.3.0/api/org/springframework/boot/builder/SpringApplicationBuilder.html
- Spring Boot 3.3, `SpringApplication` and context hierarchies: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html

**Takeaway:** `child(...)` creates a child node, `parent(...)` adds a parent node (mind the returned builder), and `sibling(...)` creates a peer node with the same parent and **can start the current node immediately when called**. Children look up to the parent to share beans, while siblings do not automatically see into each other. Good design explicitly determines **which context owns each bean, which receives arguments, which contexts have started, and who closes each context**.
