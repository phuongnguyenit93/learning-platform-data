# Distinguishing the JVM Process, Spring Boot Application, ApplicationContext, and Bean

## 1. The big picture

When running a Spring Boot application using `java -jar` or a Maven/Gradle command, four concepts often appear together yet operate at different levels:

| Concept | Nature | Who creates/manages it? | Boundaries and lifecycle |
| --- | --- | --- | --- |
| **JVM process** | An operating system process executing the Java program; it has its own PID, memory, and threads | The operating system launches the `java` program; the JVM manages the heap, GC, and Java code execution | From the moment the process starts until the process terminates |
| **Spring Boot application** | A Java program using Spring Boot to initialize configuration, infrastructure, and business logic; at runtime it is a running application instance | `main` code calls `SpringApplication.run(...)` or an equivalent bootstrap mechanism | Tied to the startup/operation of the application; not a separate OS process type |
| **`ApplicationContext`** | Spring's container: where bean definitions are registered, beans are created and wired, and configuration, events, and lifecycle management are provided | Spring creates and `refresh`es the context during bootstrap; developers can create additional contexts | From when the context is created/initialized successfully until `close`; multiple contexts can exist in one JVM |
| **Bean** | An object managed by the Spring container according to a specific bean definition and scope | `ApplicationContext`/`BeanFactory` creates, provides, injects dependencies into, and manages the lifecycle depending on scope | Depends on scope and the context containing the bean; does not automatically live for the entire JVM lifecycle |

Imagine the **common case** — a Spring Boot program running in one Java process with one main context:

```text
Operating System
└── JVM Process (has PID, heap, threads)
    └── Running Spring Boot program
        └── Main ApplicationContext
            ├── Bean: OrderService
            ├── Bean: OrderRepository
            ├── Bean: DataSource
            └── Many infrastructure beans registered by auto-configuration
```

The diagram illustrates management relationships at a conceptual level, not four objects of the same kind. **There is no rule that 1 JVM = 1 Spring Boot application = 1 context = 1 bean**: one JVM can create multiple contexts; one context contains many beans; two separate JVMs do not share Java objects in the heap.

## 2. Looking at each layer accurately

### 2.1. JVM process: operating system and memory boundary

- Running `java -jar app.jar` usually creates a separate Java process with its own PID. The JVM inside that process loads classes, runs bytecode/JIT, and manages the heap, GC, and Java threads.
- The program may use Spring Boot, plain Spring, or no Spring at all. **The JVM has no concept of a bean**; a bean is a Spring concept.
- One process can contain many HTTP-handling threads and many Java objects while still being **one** process. Creating a `Thread`, an `ExecutorService`, or a bean does not create a new JVM.
- Running the same JAR twice via two `java -jar` commands usually creates two PIDs and two independent heaps. A bean in process A is not the same object as a bean in process B.

You can inspect the PID directly in Java 17+ with `ProcessHandle.current().pid()`; at the OS level, use Task Manager, `ps`, `jps`, or `jcmd` depending on the environment. A PID only identifies the process; it does not uniquely identify individual contexts or beans.

### 2.2. Spring Boot application: program and bootstrap process

In source code, `@SpringBootApplication` typically marks the root configuration class. This annotation combines Spring Boot configuration, auto-configuration, and component scanning capabilities; **an annotation does not by itself create a JVM process**.

When `main` runs and calls `SpringApplication.run(...)`, Spring Boot sets up the environment, reads configuration sources, creates and initializes an appropriate `ApplicationContext`, registers bean definitions, processes auto-configuration, instantiates required beans, and executes startup steps. The `run` method returns a `ConfigurableApplicationContext` upon success.

A Boot application can run as a CLI/job without a web server or with an embedded servlet/reactive web server. The presence of an HTTP server does not determine whether an object is a bean. Spring Boot can also initialize child contexts or multiple contexts by design; **one application is not strictly synonymous with exactly one context**.

Distinguish two ways of speaking:

- **"Spring Boot project/application"**: source code, configuration, and deployable artifact.
- **"A running application instance/session"**: a specific execution in one or more processes depending on the deployment model. In the common JAR deployment model, one running session corresponds to one JVM process.

### 2.3. ApplicationContext: container managing Spring objects

`ApplicationContext` is a Spring interface extending the capabilities of `BeanFactory`. The context is not the operating system, the Java process, or the complete application. It holds and provides bean definitions and beans, resolves dependency injection, manages scopes, handles lifecycle callbacks, reads `Environment`/properties, and publishes application events.

Typically, the context is configured from `@Configuration`, `@Bean` methods, `@Component`/`@Service`/`@Repository` classes, imports, and auto-configuration. **A class annotated with `@Component` only becomes a bean when it is actually component-scanned/registered into the appropriate context**.

Some typical operations:

- `context.getBean(OrderService.class)`: retrieves a registered bean by type; may fail if missing or if multiple beans of the same type cannot be disambiguated.
- `context.getId()`: retrieves the context identifier, useful for diagnostics; should not be treated as a PID or guaranteed globally unique.
- `context.isActive()` on `ConfigurableApplicationContext`: checks whether the context has been initialized and is currently active.
- `context.close()`: closes the context, stops appropriate components, and invokes destroy callbacks on managed beans.

**Closing the context is not directly equivalent to calling `System.exit(...)`.** The JVM process only terminates when the JVM's exit conditions are met (e.g., no non-daemon threads remain active) or when explicitly instructed to stop. Conversely, abruptly terminating the process such as with `kill -9` may prevent Spring lifecycle callbacks from running.

### 2.4. Bean: a Java object managed by Spring

A bean is still a **Java object**, such as an `OrderService`, `DataSource`, or HTTP client. The difference is that Spring knows its bean definition, can construct the object, inject dependencies, and manage its lifecycle according to scope.

Two common ways of declaring a bean:

```java
@Service
public class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository; // constructor injection
    }
}
```

```java
@Configuration
public class AppConfig {
    @Bean
    public Clock clock() {
        return Clock.systemUTC();
    }
}
```

The snippets above **illustrate declaration styles**, not two standalone runnable programs; they require imports, `OrderRepository`, and a corresponding Spring project. `@Bean` is suitable when you want to register an object produced by a factory method, including classes from third-party libraries. `@Component` and its stereotypes are generally suitable for business classes owned by the project.

Conversely, calling `new OrderService(...)` yourself in code **does not automatically turn the new object into a Spring bean**, even if the class has `@Service`. Spring does not implicitly inject dependencies or invoke lifecycle callbacks on objects instantiated outside the container.

**Scope matters greatly:**

| Scope | Meaning for instance count |
| --- | --- |
| `singleton` (default) | Typically one instance **per bean definition per Spring container**, not a single instance across the entire JVM or cluster |
| `prototype` | The container creates a new instance each time the bean is requested; Spring does not automatically manage the full destruction phase of prototypes as it does for singletons |
| `request`, `session` | Scopes tied to a request/session in a supporting web context; not every CLI program has these scopes |

If a prototype is injected into a singleton via its constructor, the dependency is normally resolved **once when the singleton is created**; a new prototype is not automatically created on every method call. You need an appropriate lookup/provider mechanism if you want a fresh instance on demand.

## 3. Startup order and lifecycle

In a typical Spring Boot setup, the path can be read as follows:

```text
OS launches the java command
  → JVM process starts, invokes public static void main(String[] args)
  → SpringApplication.run(...)
  → Prepares Environment and startup configuration
  → Creates appropriate ApplicationContext
  → Registers bean definitions from configuration, scanning, auto-configuration
  → Refreshes context: creates/wires required non-lazy singletons, lifecycle init
  → Invokes ApplicationRunner/CommandLineRunner (if present)
  → Application is ready to serve work
  → When closing context: lifecycle shutdown, @PreDestroy/DisposableBean as applicable
  → JVM process terminates when there is no longer a reason to keep it alive
```

This is a simplified model: Spring also has events, post-processors, and distinct lifecycle phases; `lazy`/`prototype` beans may be created later. An `ApplicationContext` can close while the JVM is still running, and a single JVM can manage multiple contexts.

Distinguish these points in time:

- **JVM is running**: Java code can already execute, but a Spring context does not necessarily exist yet.
- **Context is initializing**: bean definitions may be registered, but that does not mean every bean instance has been created.
- **Context is refreshed and active**: most eager singletons have been created; startup runners and related tasks may still run after refresh.
- **Application is ready**: typically after startup runners complete, Spring Boot publishes `ApplicationReadyEvent`.
- **Shutdown**: closing the context releases bean resources according to lifecycle rules; when the JVM stops depends on remaining threads and how the application is run.

## 4. Runnable Spring Boot 3.x / Java 17+ example

In a Spring Boot project using Java 17 or later with the `spring-boot-starter` dependency (additional starters may be added), place the following two files in the `com.example.runtime` package. The example intentionally uses `WebApplicationType.NONE` so no web server is started, allowing you to observe only the runtime layers. It can be run using the Spring Boot Gradle or Maven plugin.

**File `src/main/java/com/example/runtime/RuntimeDemoApplication.java`**

```java
package com.example.runtime;

import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class RuntimeDemoApplication {

    public static void main(String[] args) {
        // The JVM is already running before ApplicationContext is created.
        System.out.println("JVM PID positive: " + (ProcessHandle.current().pid() > 0));

        try (ConfigurableApplicationContext context =
                new SpringApplicationBuilder(RuntimeDemoApplication.class)
                        .web(WebApplicationType.NONE)
                        .run(args)) {

            GreetingService first = context.getBean(GreetingService.class);
            GreetingService second = context.getBean(GreetingService.class);

            System.out.println("Context active: " + context.isActive());
            System.out.println("Same singleton: " + (first == second));
            System.out.println(first.message());
        } // context.close() is called automatically here.
    }
}
```

**File `src/main/java/com/example/runtime/GreetingService.java`**

```java
package com.example.runtime;

import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
public class GreetingService {

    public String message() {
        return "Hello from Spring bean";
    }

    @PreDestroy
    public void onDestroy() {
        System.out.println("Bean destroyed");
    }
}
```

Run using one of the commands corresponding to a **project that already has the Spring Boot Gradle/Maven plugin and wrapper**:

```bash
# macOS/Linux, Gradle project
./gradlew bootRun

# macOS/Linux, Maven project
./mvnw spring-boot:run
```

```powershell
# Windows, Gradle project
.\gradlew.bat bootRun

# Windows, Maven project
.\mvnw.cmd spring-boot:run
```

The lines printed by the **example code** have the following order and values; Spring Boot may print a banner or startup logs in between:

```text
JVM PID positive: true
Context active: true
Same singleton: true
Hello from Spring bean
Bean destroyed
```

**Explanation of each piece of evidence:**

1. The PID line is printed **before** `SpringApplicationBuilder.run(...)`: the JVM process already exists even before any context exists.
2. The `run` call initializes the Boot application and returns an active context.
3. Calling `getBean(GreetingService.class)` twice returns the same reference because `GreetingService` is a default singleton **within this context**. That says nothing about beans in another context.
4. The `message()` method is ordinary Java object behavior; Spring manages how the object is obtained and its lifecycle.
5. Exiting the `try` block calls `close` on the context, so Spring invokes `@PreDestroy` for this singleton and prints `Bean destroyed`. Afterward `main` finishes; in this non-web example there is no other background work keeping the JVM alive.

If you create two independent `ApplicationContext` instances and register the same singleton bean definition in each context, the typical result is **two distinct instances**: repeated `getBean` calls in context A return instance A, while in context B they return instance B. If parent-child contexts are used, the child context can also access beans from the parent; in that case you must distinguish which container owns a bean.

## 5. Choosing the right concept when diagnosing errors

| Symptom / question | Layer to check | Correct reasoning |
| --- | --- | --- |
| Java process exhausts heap or disappears from PID list | **JVM process** | Check PID, heap, thread dump, GC, exit code; not enough evidence yet to blame a specific bean |
| `SpringApplication.run` fails or fails to start web server | **Boot bootstrap / context refresh** | Read the root exception, configuration, dependencies, bean creation, or port binding error |
| `NoSuchBeanDefinitionException` | **ApplicationContext / bean registration** | Check whether the bean was scanned/declared and auto-configuration conditions were met; do not infer that the JVM is not running |
| `NoUniqueBeanDefinitionException` | **Bean resolution** | Multiple beans match an injection point; use `@Qualifier`/`@Primary` or redesign the dependency |
| Dependency is `null` after calling `new SomeService()` directly | **Bean management** | The object was instantiated outside the container; prefer constructor injection and let Spring create the object |
| A service retains state across requests | **Bean scope and thread safety** | Singletons are normally shared across many requests/threads; avoid mutable per-request state in a singleton |
| Running the same JAR in two different containers/Pods | **Multiple JVM processes and multiple contexts** | Heap and bean instances are not shared; sharing state requires an appropriate external system |
| Context is closed yet the process has not exited | **Context lifecycle vs. JVM lifecycle** | Check non-daemon threads or other tasks; `close()` is not a command to terminate the OS process |

## 6. Misconceptions to avoid

- **"Spring Boot is the JVM."** False: Spring Boot is a framework/bootstrap mechanism running **inside** the JVM; it does not replace the JVM.
- **"Having `@Service` means every object of that class is a bean."** False: Spring must manage the specific instance; `new` outside the context still produces a plain Java object.
- **"Singleton means a single object across the entire system."** False: Spring's singleton scope is tied to a bean definition and container; multiple contexts, processes, or deployed instances can each have their own singletons.
- **"The context is all the beans."** Inaccurate: the context is the container and management mechanism; beans are the objects provided by the container.
- **"All beans are created as soon as the JVM runs."** False: the JVM starts first; many eager singletons are created during context refresh, while lazy/prototype/request-scoped beans have different creation times.
- **"Creating a thread, request, or bean creates another Boot app/JVM."** False: threads and requests are typically handled within the existing process and context; bean scopes may differ without creating another JVM.
- **"Closing a context always shuts down the entire process."** False: a JVM may have additional contexts or other worker threads; in an application with only one non-web context and no remaining keep-alive threads, the process will exit after `main` completes.

## 7. Self-check questions

1. **Why can `main` print the PID before calling `SpringApplication.run`?** Because the JVM is created and begins executing Java code before Spring Boot bootstraps the context.
2. **If a singleton bean is injected into two services in the same context, are they two objects?** By default they are the same object for the same bean definition; inspect proxies, scopes, and actual configuration when comparing identity.
3. **Do two `java -jar app.jar` processes share a singleton `UserService`?** No: they have separate heaps and contexts. Sharing data across processes requires a mechanism outside the JVM such as a database, cache, or messaging.
4. **Does a class annotated with `@Component` outside the component scan automatically become a bean?** No, unless registered through another mechanism.
5. **When `@PreDestroy` does not run after `kill -9`, does that prove the bean is not managed by Spring?** No: the process was terminated abruptly and had no chance to perform a normal shutdown.

**Takeaway:** The JVM is the process environment executing Java; Spring Boot starts the application on top of that environment; `ApplicationContext` is the initialized Spring container; a bean is an object managed by the container. To determine lifecycle or state-sharing scope, always ask whether you are talking about **the process, the context, the bean definition, or a bean instance**.
