# Closing a Spring ApplicationContext with try-with-resources — Spring Core Container

## 1. Objective and Use Case

You already know how to create a Spring IoC container to register and retrieve beans. The next step is **ending the container lifecycle properly**. A Java application that runs a task and exits can instantiate `AnnotationConfigApplicationContext` itself; when finished, it should **close the context** so Spring has the chance to run bean destruction callbacks, release bean-managed resources, and mark the context inactive.

**Try-with-resources** is the right Java construct when your code **owns the context's lifecycle**: closing the context cleanly by lexical block scope rather than remembering to call `close()` across multiple exit paths.

By the end of this lesson, you will be able to:

- Distinguish **closing a Spring context** from merely returning from `main`, dropping references, or letting the JVM exit.
- Use both `try (AnnotationConfigApplicationContext context = ...)` and `try (context)` syntax in Java 17.
- Explain why a Spring context is closeable via `AutoCloseable`/`Closeable`, and that `close()` runs even when the `try` body exits via an exception.
- Run a pure Spring Framework application with a bean configured with `@Bean(destroyMethod = "shutdown")` and **observe stdout ordering**.
- Close the context even when `register(...)` / `refresh()` happens inside the block and might fail.
- Recognize limitations: `prototype` beans are not fully destroyed by Spring, objects created outside the container are not managed automatically, and `System.exit`/crashes are not normal cleanup paths.
- Know when **not to close** a context because its lifecycle belongs to Spring Boot, Spring Test, a host framework, or another component.

**Scope:** This lesson focuses on lifecycle and `try-with-resources` in **Spring Core Container**. You do not need Spring Boot, an HTTP server, a database, transactional APIs, or complex shutdown hooks to learn this skill.

## 2. Whoever Owns the Context Is Responsible for Closing It

A common example:

~~~java
AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext(AppConfig.class);
GreetingService service = context.getBean(GreetingService.class);
System.out.println(service.greet("Lan"));
// If execution ends without closing, the container is not explicitly asked to clean up.
~~~

**The snippet above is illustrative only**, omitting `AppConfig`, `GreetingService`, and a complete Java file. When the application owns the context object, make sure `context.close()` is invoked.

Why not just wait for the garbage collector?

- The garbage collector reclaims **eligible Java memory**, and has no responsibility for calling bean destruction callbacks.
- Beans may hold **connection pools, file handles, background executors, sockets, caches, or threads**; some resources require orderly shutdown to stop work or flush data.
- Java does not guarantee `finalize()` as a safe resource-management mechanism; never rely on finalization instead of `close()`.
- Short-lived applications may terminate before any garbage collection helps; long-lived applications may retain resources through live references.

**Distinguish two kinds of ownership:**

| Who Created/Manages the Context? | Who Decides When to Close It? |
| --- | --- |
| Your own Java code creating `new AnnotationConfigApplicationContext()` to run a task | That same code, typically via `try-with-resources` |
| A library creating an internal context and returning a service to you | Follow the library's contract; do not arbitrarily close the library's context |
| Spring Boot / a host framework creating the main `ApplicationContext` | The framework/lifecycle owner usually decides shutdown; do not close inside a request-handling service |
| Spring Test managing and caching the test context | The test infrastructure manages it; do not close it after every test if the framework reuses it |

If a service receives `ApplicationContext` from elsewhere and calls `close()`, it can **shut down the entire application** or break beans other components still need. Do not turn closing the context into a responsibility of arbitrary business beans.

## 3. Two Valid try-with-resources Styles in Java 17

### 3.1. Declaring the Resource Inside the try Parentheses

~~~java
try (AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext(AppConfig.class)) {

    GreetingService service = context.getBean(GreetingService.class);
    System.out.println(service.greet("Lan"));
} // Java calls context.close() when leaving the block normally.
~~~

**This is a snippet**, missing imports and business classes. `AnnotationConfigApplicationContext` belongs to Spring Framework and satisfies the `AutoCloseable` contract via the context interfaces. Java invokes `close()` automatically when exiting the block, even if code inside the `try` body throws an exception.

**Bootstrap warning:** the constructor `new AnnotationConfigApplicationContext(AppConfig.class)` immediately registers and refreshes. If construction/refresh **throws an exception before the object is successfully assigned to the `try` resource**, that resource was never established inside `try-with-resources`; do not claim this form always closes a context whose creation failed partway through.

### 3.2. Using a Previously Declared Local Variable: try(context)

Since Java 9 (including Java 17), you can write:

~~~java
AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext();

try (context) {
    context.register(AppConfig.class);
    context.refresh();
    GreetingService service = context.getBean(GreetingService.class);
    System.out.println(service.greet("Lan"));
}

System.out.println("active=" + context.isActive());
~~~

This is also a snippet; the complete program is in Section 5.

- The `context` variable must be **final or effectively final** (never reassigned after initialization) to use `try (context)`.
- With the **no-arg constructor**, the context is created but **not refreshed yet**. Placing `register(AppConfig.class)` and `refresh()` **inside the block** ensures that even if refresh fails, the resource is already tracked so `try-with-resources` will attempt to close it.
- On normal completion and block exit, `close()` has been called. `isActive()` then returns `false` in this `AnnotationConfigApplicationContext` example.
- The `context` variable remains in scope afterward only because it was declared outside; **do not keep using it to look up beans**, because the context is closed.

### 3.3. Comparison with try-finally

Older Java code commonly wrote:

~~~java
AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext();
try {
    context.register(AppConfig.class);
    context.refresh();
    // Use beans.
} finally {
    context.close();
}
~~~

Once the context is instantiated, this also intends to clean up. However, `try-with-resources` is more concise, clearly expresses **resource ownership scope**, uses Java's standard `close()` mechanism, and defines formal semantics when both the body and closing the resource throw exceptions.

**One intentional close** is enough. Do not add `context.close()` inside a `try (context)` block “just to be sure”; it hurts readability and confuses learners about lifecycle ordering.

## 4. What Happens When the Context Closes?

For an `AnnotationConfigApplicationContext` that refreshed successfully, `close()` runs Spring's context shutdown sequence. Under normal conditions, Spring:

1. Signals and executes the appropriate shutdown/lifecycle phases for the context.
2. Stops lifecycle beans/components when configured accordingly.
3. Executes destruction callbacks on **managed singletons** that declare eligible destruction hooks (e.g., via `@Bean(destroyMethod = "...")`, `DisposableBean`, or `@PreDestroy` when annotation support is enabled).
4. Releases internal context-lifecycle resources and marks the context inactive.

Not **every bean** has a destroy callback. A bean holding only immutable values usually needs nothing done at shutdown. The container cannot automatically close a resource created outside the context and stored in a global variable.

### Closing the Context Is Not Closing Every Object Manually

In the demo there will be a `ManagedAudit` bean with the method:

~~~java
public void shutdown() {
    System.out.println("destroy=ManagedAudit");
}
~~~

As a snippet inside a class, this method by itself is just Java. When the factory method carries the annotation:

~~~java
@Bean(destroyMethod = "shutdown")
public ManagedAudit managedAudit() {
    return new ManagedAudit();
}
~~~

Spring registers a **destroy callback** for that managed bean. When closing a context containing that created singleton bean, Spring calls `shutdown()`. You **do not** need to retrieve the bean and call `shutdown()` manually in `main`.

**Do not confuse `@Bean(destroyMethod=...)` with `@PreDestroy`**: both can specify destruction work under supported conditions, but `@PreDestroy` requires the matching Jakarta annotation in Spring 6+, whereas this demo uses explicit `destroyMethod="shutdown"` without depending on lifecycle annotations outside the current module.

## 5. Complete Project: Observing the Destroy Callback on Stdout

Use **JDK 17+, Maven, and Spring Framework 7.0.9** (`spring-context` module). This example version is pinned so commands and dependencies are reproducible, **not a claim about the latest Spring release**. No Spring Boot, database, or HTTP server is needed.

Directory layout:

~~~text
context-close-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ContextCloseDemo.java
~~~

### 5.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>context-close-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>7.0.9</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.ContextCloseDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Maven resolves `spring-context` and its required transitive dependencies. Compiling manually with `javac` requires the corresponding classpath; adding only a single Spring JAR is usually insufficient.

### 5.2. src/main/java/demo/ContextCloseDemo.java

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class ContextCloseDemo {
    private ContextCloseDemo() {}

    public interface GreetingRepository {
        String message(String name);
    }

    public static final class SimpleGreetingRepository
            implements GreetingRepository {
        @Override
        public String message(String name) {
            return "Xin chao, " + name + "!";
        }
    }

    public static final class ManagedAudit {
        private final List<String> events = new ArrayList<>();

        public void record(String name) {
            events.add(name);
        }

        public List<String> snapshot() {
            return List.copyOf(events);
        }

        public void shutdown() {
            System.out.println("destroy=ManagedAudit");
        }
    }

    public static final class GreetingService {
        private final GreetingRepository repository;
        private final ManagedAudit audit;

        public GreetingService(
                GreetingRepository repository, ManagedAudit audit) {
            this.repository = Objects.requireNonNull(repository);
            this.audit = Objects.requireNonNull(audit);
        }

        public String greet(String input) {
            if (input == null || input.isBlank()) {
                throw new IllegalArgumentException("name must not be blank");
            }
            String name = input.strip();
            String message = repository.message(name);
            audit.record(name);
            return message;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public GreetingRepository greetingRepository() {
            return new SimpleGreetingRepository();
        }

        @Bean(destroyMethod = "shutdown")
        public ManagedAudit managedAudit() {
            return new ManagedAudit();
        }

        @Bean
        public GreetingService greetingService(
                GreetingRepository repository, ManagedAudit audit) {
            return new GreetingService(repository, audit);
        }
    }

    public static void main(String[] args) {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();

        try (context) {
            context.register(AppConfig.class);
            context.refresh();

            GreetingService service = context.getBean(GreetingService.class);
            ManagedAudit audit = context.getBean(ManagedAudit.class);

            System.out.println("insideActive=" + context.isActive());
            System.out.println("singleton=" +
                    (service == context.getBean(GreetingService.class)));
            System.out.println("greeting=" + service.greet(" Lan "));
            System.out.println("audit=" + audit.snapshot());
        }

        System.out.println("afterActive=" + context.isActive());
    }
}
~~~

**Key points to understand before running:**

- `new AnnotationConfigApplicationContext()` creates an unrefreshed context; `register(AppConfig.class)` and `refresh()` sit inside `try (context)`.
- The `greetingRepository` bean provides `GreetingRepository`. The `managedAudit` bean is configured to invoke `shutdown()` when Spring destroys singletons.
- The `greetingService` bean receives repository and audit via factory method parameters. The service **never queries `ApplicationContext` directly** and does not manage the audit lifecycle itself.
- `ManagedAudit` is just a Java object with a `shutdown()` method; Spring knows to call it thanks to `@Bean(destroyMethod="shutdown")` metadata.
- Inside `try`, the service records a normalized name into audit; at the end of the block, **Java invokes `context.close()`**, and Spring executes the audit destroy callback **before** code outside the block prints `afterActive=false`.
- To keep output order deterministic, only one bean prints a message in its destroy callback. This lesson does not rely on the initialization order of independent singletons.

### 5.3. Running with Maven

From the `context-close-demo` directory:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

**Exact stdout printed by the Java program on a successful run:**

~~~text
insideActive=true
singleton=true
greeting=Xin chao, Lan!
audit=[Lan]
destroy=ManagedAudit
afterActive=false
~~~

These six lines are output from the `System.out.println(...)` calls in the demo code. JDK/Maven version lines and tool/framework logging (if configured) **do not count** as output printed by the demo code itself. Spring executes the destroy callback when the context closes; `destroy=ManagedAudit` does **not** mean Java automatically calls `shutdown()` on every object with a method of that name.

### 5.4. Compiling and Running Manually with javac/java

Because it imports Spring APIs, it must be compiled and run with Spring JARs and their transitive dependencies. Have Maven write the classpath file first:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

**Linux/macOS (bash/zsh):**

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -cp "$(cat classpath.txt)" \
  -d out src/main/java/demo/ContextCloseDemo.java
java -cp "out:$(cat classpath.txt)" demo.ContextCloseDemo
~~~

**Windows PowerShell:**

~~~powershell
$deps = (Get-Content -Raw classpath.txt).Trim()
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -cp "$deps" -d out src/main/java/demo/ContextCloseDemo.java
java -cp "out;$deps" demo.ContextCloseDemo
~~~

The classpath separator is `:` on Linux/macOS and `;` on Windows. Both ways invoke the same `main`, so the six stdout lines produced by the code do not change.

## 6. Timeline: try-with-resources and the Spring Destroy Callback

~~~mermaid
sequenceDiagram
    participant M as main()
    participant J as Java try-with-resources
    participant C as ApplicationContext
    participant S as GreetingService
    participant A as ManagedAudit
    M->>J: try (context)
    J->>C: register(AppConfig) / refresh()
    C->>S: create bean + inject dependencies
    M->>S: greet(" Lan ")
    S->>A: record("Lan")
    M-->>J: exit try body
    J->>C: close()
    C->>A: shutdown() (destroy callback)
    A-->>M: println destroy=ManagedAudit
    M->>C: isActive()
    C-->>M: false
~~~

This models the steps directly relevant to the example and **does not describe all Spring lifecycle internals**. Java is responsible for calling `close()` per `try-with-resources`; Spring is responsible for translating closing the context into callbacks on the beans it manages.

To avoid confusion:

- `GreetingService.greet(...)` runs **because `main` calls it**, not because the container created the bean.
- `ManagedAudit.shutdown()` runs **because the context closed and the bean has destroy metadata**, not because the Java variable `audit` went out of scope.
- `context.isActive()` reflects **context state**, not a check of whether each bean object still exists in memory. Object references may still exist after the context closes, but using shut-down collaborators is unsafe or violates their contract.

## 7. When an Exception Occurs: What Does Java Guarantee?

Try-with-resources is designed so registered resources are **closed on block exit as a language mechanism**, even when the `try` body fails:

~~~java
AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext();

try (context) {
    context.register(AppConfig.class);
    context.refresh();
    throw new IllegalStateException("example failure");
} // Java still calls context.close() when exiting due to an exception.
~~~

This is an **illustrative snippet** to observe Java semantics; it throws an exception and does not produce the “happy path” stdout. Do not paste it directly into the main program while comparing against the six expected output lines.

If you need to catch application errors at the boundary, use:

~~~java
AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext();

try (context) {
    context.register(AppConfig.class);
    context.refresh();
    // Use beans; may throw an error.
} catch (RuntimeException failure) {
    System.err.println("Job failed: " + failure.getClass().getSimpleName());
}
~~~

In Java, **the resource is closed before the outer `catch` block handles the exception**. Whether catching and continuing makes sense depends on business requirements; never swallow a Spring bootstrap failure and keep running with a null service.

### Suppressed Exceptions Are a Java Rule, Not a Guarantee for Every Spring Destroy Callback

If the **`try` body** throws exception A and the resource's **`close()`** also throws exception B outward, Java keeps A as the primary exception and attaches B under `A.getSuppressed()`. This is **general Java try-with-resources behavior**.

In Spring, exceptions from bean destroy callbacks may be logged or handled internally by the framework; **do not assume** every individual bean shutdown error will appear in `getSuppressed()` on the `try`-body exception. When debugging context closure, check the specific logs and callbacks.

**Critical limitation:** `try-with-resources` cannot guarantee callbacks run if the entire JVM/process is terminated abruptly, via `Runtime.halt(...)`, power loss, or a crash. Java's guarantee applies to **normal or exception control flow** actually exiting the block after the resource has been registered with `try`.

## 8. Placing refresh() Inside the Block to Handle Bootstrap Failures

Compare the two styles:

**Short form for very small examples:**

~~~java
try (AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext(AppConfig.class)) {
    // Context is already refreshed when the constructor returns successfully.
}
~~~

**Form that brings startup inside the cleanup scope:**

~~~java
try (AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext()) {
    context.register(AppConfig.class);
    context.refresh();
    // Run the task.
}
~~~

If `refresh()` inside the `try` body throws an error, the context resource was already created and attached to `try-with-resources`, so Java still calls `close()` on exit. This **does not mean failed beans finished constructing or get full destroy callbacks**; Spring has its own cleanup phases when refresh fails.

The second form also makes dynamic configuration steps clearer:

~~~java
try (AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext()) {
    context.register(AppConfig.class);
    context.refresh();
    System.out.println(context.containsBean("greetingService"));
}
~~~

This snippet runs inside a program that has `AppConfig`, **not as a standalone file**. Never call `refresh()` repeatedly on the same `GenericApplicationContext/AnnotationConfigApplicationContext`; contexts in this family enforce single-refresh semantics.

## 9. Scope and Limits of Destruction Management

| Case | Behavior to Remember |
| --- | --- |
| Managed singleton already created, with destroy callback | Context normally calls the callback on clean close |
| Bean with no callback or private resources | No message printed or special destruction work needed |
| Prototype bean created by Spring and handed to caller | Spring generally **does not manage full prototype destruction** afterward; the caller is responsible as needed |
| Object instantiated via `new` outside container | Does not automatically receive Spring destroy callbacks |
| Resource opened by a bean but never closed properly by it | Closing the context cannot fix missing resource cleanup in bean code |
| Context owned by another framework | Do not arbitrarily use `try-with-resources` to close a context other components still use |

### Prototypes Are an Important Exception

~~~java
@Bean
@org.springframework.context.annotation.Scope("prototype")
SomeWorker someWorker() {
    return new SomeWorker();
}
~~~

This is an illustrative snippet only; `SomeWorker` is not defined in this example. Spring creates prototypes on demand, but **does not run full destruction lifecycle callbacks** for prototypes after handing the object to the caller. If `SomeWorker` owns files or sockets, the code holding the object or a dedicated resource-management mechanism must handle closing them.

Do not read “closing the context closes all beans” as applying indiscriminately to every scope and every Java-created object.

### Should You Use @PreDestroy Instead of @Bean(destroyMethod)?

You can, if the bean is managed by the container and the application has the appropriate annotation API. In Spring Framework 6+, the standard annotation is `jakarta.annotation.PreDestroy`, **not the legacy `javax.annotation.PreDestroy`**. Using it requires the corresponding dependency/annotation processing in your environment.

In this lesson, `@Bean(destroyMethod="shutdown")` is the simplest choice to show directly how a callback is defined in Java configuration without adding extra annotation libraries.

Beans can also implement `DisposableBean` or a Java interface like `AutoCloseable`; Spring can also auto-infer certain `close`/`shutdown` destroy methods in eligible cases. However, **do not rely on implicit inference for examples needing deterministic output**: specify the method explicitly while learning the mechanism.

## 10. Common Mistakes and How to Fix Them

| Mistake | Consequence | Right Approach |
| --- | --- | --- |
| Creating a context in a short task and never closing it | Destroy callbacks/resource cleanup may never run intentionally | Use `try-with-resources` or `finally { context.close(); }` |
| Closing the context immediately after returning a bean to a caller | Bean is used after the container has shut down | Let the context creator/owner decide its lifecycle |
| Service calls `context.close()` after one request | Shuts down the shared container and breaks other requests | Never put context-closing responsibility inside business services |
| Calling `context.close()` both inside `try` and via TWR exit | Redundant destruction intent; harder to reason about | Let TWR handle `close()` once structurally |
| Assuming every `@Bean` prints something on close | Beans without callbacks produce no output | Attach `destroyMethod` or an appropriate callback when cleanup work is needed |
| Equating `close()` with garbage collection | Confuses heap reclamation with off-heap/lifecycle resources | Separate GC-eligible objects from bean shutdown operations |
| Expecting prototypes to be automatically destroyed | Prototype resources leak if forgotten | Give ownership to the caller or use an appropriate scope/mechanism |
| Using the auto-refreshing constructor and assuming all creation errors are cleaned up by TWR | Constructor can fail before becoming a valid resource | When managing bootstrap errors, create an unrefreshed context and `register/refresh` inside `try` |
| Reusing a context after close | Bean lookups or lifecycle APIs are no longer usable | Create a new context in a new session when needed |
| Using `System.exit(0)` as a cleanup strategy | Can bypass normal Java unwinding paths | Exit normally via return/exception so TWR closes structurally |
| Misconfiguring `destroyMethod` | Bean creation error or callback not invoked as expected | Use the exact method name, avoiding parameters or typos |
| `javac` reports missing Spring packages | Classpath error, not a `close()` error | Use Maven or build the full transitive classpath |

**Do not treat `close` as a cure-all:** if a bean fails to close its own socket/file according to its contract, the container cannot fix that logic for you. Write unit tests for resource-owning objects and smoke tests for context shutdown.

## 11. Comparing Three Ways to End the Lifecycle

| Approach | Pros | Limitations |
| --- | --- | --- |
| `try (context) { ... }` | Clear ownership, closes by lexical scope, idiomatic Java 17 | Use only when the context is genuinely owned by that block |
| `try { ... } finally { context.close(); }` | Works in older code and complex patterns | More boilerplate; easy to get `finally` wrong if sloppy |
| `context.registerShutdownHook()` | Registers a JVM shutdown hook to close on normal JVM exit | Does not replace intentional closing for short tasks; not guaranteed on terminate/crash/`kill -9` |

Avoid routinely mixing `registerShutdownHook()` with TWR on the same context without a clear reason; it blurs ownership and callback timing expectations. Spring guards internal shutdown state, but **clear single ownership** is always easier to test.

If you write a long-running application whose lifecycle is coordinated by a framework, follow the framework's and deployment infrastructure's shutdown mechanisms rather than closing the app context after a single request.

## 12. Extended Practice and Output QA

### Exercise 1: Adding Another Callback

Register a secondary bean `TaskRecorder` with its own destroy callback and inject it into `GreetingService`. Run and observe the actual callback order. **Do not rely on method declaration order** as an ordering contract. If bean B depends on A and both have lifecycle hooks, dependency relationships can influence destruction order, so design around real dependencies rather than coincidental logs.

### Exercise 2: Throwing an Exception Inside the try Body

In the demo program, replace `service.greet(" Lan ")` with a statement throwing `IllegalStateException` **after `context.refresh()` succeeds**. Observe that the `destroy=ManagedAudit` callback still runs as Java unwinds the exception. Do not compare against the six happy-path lines in this negative test.

### Exercise 3: Making refresh Fail

Create a `@Bean` requiring a mandatory dependency not registered in configuration. Use the pattern of creating an unrefreshed context and calling `refresh()` **inside `try`**. Observe the context failing fast; do not assume a destroy callback for an uncreated bean will appear.

### Exercise 4: Running with a Different Input Name

In the happy path, change `" Lan "` to `" Minh "`. Predict the two lines that change:

~~~text
greeting=Xin chao, Minh!
audit=[Minh]
~~~

The context/singleton status lines and `destroy=ManagedAudit` remain unchanged under the same configuration.

### Exercise 5: Writing a Shutdown Verification Test

With a test-created Spring context, you can use a fake bean holding a boolean `closed` flag with a destroy callback to prove `closed==true` after leaving `try`. Avoid calling business methods on an already-closed resource just for testing.

### Mastery Checklist

- [ ] Know who **owns the context** and why it needs to be closed.
- [ ] Distinguish context `close()` from garbage collection.
- [ ] Use `try-with-resources` with a context implementing `AutoCloseable`.
- [ ] Understand the difference between `try (Type resource = ...)` and Java 9+'s `try (resource)`.
- [ ] For bootstrap errors, know how to place `register/refresh` inside a `try` block that already owns the resource.
- [ ] Attach an explicit callback via `@Bean(destroyMethod="shutdown")`.
- [ ] Run on JDK 17+ with Maven or `javac`/`java` with the Spring classpath.
- [ ] Verify all **six stdout lines** of the example.
- [ ] Distinguish singleton destruction from prototypes and non-managed objects.
- [ ] Never close a context supplied by a framework or external owner you do not own.
- [ ] Never expect TWR to always clean up when the JVM is killed or crashes.
- [ ] Know how to use logs and tests to verify callbacks instead of guessing.

**Conclusion:** Try-with-resources is not a Spring annotation; it is a **Java language mechanism** guaranteeing `close()` is called on a registered resource upon exiting a block. Because a Spring context implements the closeable contract, that Java mechanism triggers **Spring's shutdown sequence**, including destroy callbacks on eligible managed beans. Always **close the context where it is owned**, not everywhere beans are used.

### Official Documentation

- [Spring — Shutting Down the Container Gracefully](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring — Using @Bean](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
- [Spring — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Java Language Guide — try-with-resources](https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html)
