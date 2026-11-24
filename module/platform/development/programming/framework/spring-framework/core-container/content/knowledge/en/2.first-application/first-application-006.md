# Observing Object Creation and Dependency Injection in Spring Core Container

## 1. Objective: See IoC/DI in Action, Not Just Memorize Annotations

When a Java application uses the **Spring IoC Container**, objects managed by the container are called **beans**. The container reads configuration, creates objects when needed, finds matching dependencies, and supplies them to dependent objects. **Dependency Injection (DI)** is how an object receives its dependencies from outside instead of instantiating everything inside business logic.

This lesson focuses on **empirical evidence**: using constructor counters, an event trace list, reference equality (`==`), and CLI output to answer:

- **When** is the `Repository` bean created, and how many times?
- **Which exact `Repository` object** does `GreetingService` receive?
- Does calling `getBean` twice on a singleton create another service?
- Does a `prototype` bean produce a new instance on every lookup?
- Does a `@Lazy` bean have a **definition** registered yet **no instance** created when the context refreshes?
- At what moment does closing the context invoke destroy callbacks?

Do not confuse three distinct levels: a **Java class** is a type, a **bean definition** is container configuration used to create/manage a bean, and a **bean instance** is the actual object created. Having a definition **does not mean** an instance exists yet. A `prototype` bean definition can yield many instances; a default `singleton` bean is shared **per definition, within one container**, not as one object across the entire JVM.

**Scope:** pure Spring Framework Core Container, without Spring Boot, an HTTP server, or a database. Examples use Java 17+, Maven, `spring-context`, and `AnnotationConfigApplicationContext`. Key results are verified from stdout printed by the program itself; background logs from the build tool or libraries are not part of expected stdout.

## 2. Read the Relationship Diagram Before Inspecting Logs

The example has four beans:

~~~text
                  AnnotationConfigApplicationContext
                              |
                    AppConfig (@Configuration)
                              |
              +---------------+---------------+
              |               |               |
        repository        greetingService     report
        singleton         singleton          prototype
              |               |                 |
              +---inject----->|            each getBean
                              |            creates new object
                              |
                          greet("An")
                              |
                         "data:An"

                      audit (singleton @Lazy)
                          |
              not needed at refresh;
              created on first getBean
~~~

The `@Bean` factory methods declare `repository`, `greetingService`, `report`, and `audit`. The factory method for `greetingService` accepts a **`Repository` parameter**. Spring resolves a matching bean and passes the **actual reference** into the factory method call, and from there into the service constructor.

To observe every angle, the demo will:
1. Create an **empty** context and call `register(AppConfig.class)`.
2. Print counters **before `refresh()`**.
3. Call `refresh()` to bootstrap the context and create **non-lazy** singletons.
4. Print counters, the creation trace, and registration status of the `audit` bean.
5. Retrieve `GreetingService` and `Repository`; compare the injected reference.
6. Retrieve `Report` twice, then request the lazy `Audit` bean.
7. Close the context via `try-with-resources` and observe the destroy callback.

We **do not depend on the order of Spring's internal beans** or the framework's bean definition count. Counters are placed only inside constructors of **our demo classes**, so container infrastructure creates no noise.

## 3. Setting Up the Standalone Maven Project

Requires **JDK 17+**, **Maven 3.9+**, and internet access on the first run to download dependencies (or an available Maven mirror). Verify your environment:

~~~bash
java -version
javac -version
mvn -version
~~~

Environment check commands have no fixed stdout. If `mvn -version` shows a different Java version from `java -version`, check `JAVA_HOME`, `PATH`, and toolchain settings.

Create the directory tree:

~~~text
bean-observation-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── BeanObservationDemo.java
~~~

Complete `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bean-observation-demo</artifactId>
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
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.BeanObservationDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` provides `AnnotationConfigApplicationContext`, `@Configuration`, and `@Bean`, and pulls in required modules via its dependency graph. You do not need `spring-boot-starter`; Maven/Gradle resolves the classpath automatically. `maven.compiler.release=17` compiles against Java 17 APIs.

**Spring Framework 7.0.9** is pinned so the example is reproducible; it supports Java 17. For real production software, use supported patch releases and align Spring modules using an appropriate BOM/dependency management.

## 4. Java 17 Code: Recording Object Creation Timing

Create the exact file `src/main/java/demo/BeanObservationDemo.java`:

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;

import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;
import org.springframework.context.annotation.Scope;

public final class BeanObservationDemo {
    private BeanObservationDemo() {
    }

    // Counters and trace are only for a single-threaded demo program.
    private static final List<String> TRACE = new ArrayList<>();
    private static int repositoryCreated;
    private static int serviceCreated;
    private static int reportCreated;
    private static int auditCreated;

    public static final class Repository {
        private final int id;

        public Repository() {
            id = ++repositoryCreated;
            TRACE.add("repository#" + id);
        }

        public int id() {
            return id;
        }

        public String load() {
            return "data";
        }

        public void shutdown() {
            System.out.println("destroy.repository#" + id);
        }
    }

    public static final class GreetingService {
        private final Repository repository;
        private final int id;

        public GreetingService(Repository repository) {
            this.repository = repository;
            id = ++serviceCreated;
            TRACE.add("service#" + id + "(repository#" + repository.id() + ")");
        }

        public Repository repository() {
            return repository;
        }

        public String greet(String name) {
            return repository.load() + ":" + name;
        }
    }

    public static final class Report {
        private final int id;

        public Report() {
            id = ++reportCreated;
        }

        public int id() {
            return id;
        }
    }

    public static final class Audit {
        public Audit() {
            auditCreated++;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean(destroyMethod = "shutdown")
        public Repository repository() {
            return new Repository();
        }

        // Spring supplies Repository via the factory method parameter.
        @Bean
        public GreetingService greetingService(Repository repository) {
            return new GreetingService(repository);
        }

        @Bean
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        public Report report() {
            return new Report();
        }

        @Bean
        @Lazy
        public Audit audit() {
            return new Audit();
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext()) {
            context.register(AppConfig.class);

            System.out.println("beforeRefresh.repository=" + repositoryCreated);
            System.out.println("beforeRefresh.service=" + serviceCreated);

            context.refresh();

            System.out.println("afterRefresh.repository=" + repositoryCreated);
            System.out.println("afterRefresh.service=" + serviceCreated);
            System.out.println("afterRefresh.report=" + reportCreated);
            System.out.println("afterRefresh.audit=" + auditCreated);
            System.out.println("creation.trace=" + String.join(" > ", TRACE));
            System.out.println("definition.audit="
                    + context.containsBeanDefinition("audit"));

            Repository repository = context.getBean(Repository.class);
            GreetingService first = context.getBean(GreetingService.class);
            GreetingService second = context.getBean(GreetingService.class);

            System.out.println("sameService=" + (first == second));
            System.out.println("sameInjectedRepository="
                    + (first.repository() == repository));
            System.out.println("greeting=" + first.greet("An"));

            Report reportA = context.getBean(Report.class);
            Report reportB = context.getBean(Report.class);

            System.out.println("report.ids="
                    + reportA.id() + "," + reportB.id());
            System.out.println("sameReport=" + (reportA == reportB));

            Audit audit = context.getBean(Audit.class);
            System.out.println("afterLookup.audit=" + auditCreated);
            System.out.println("sameAuditSingleton="
                    + (audit == context.getBean(Audit.class)));
        }

        System.out.println("context.closed=true");
    }
}
~~~

### Why Is This Instrumentation Trustworthy?

- Only **`Repository`'s constructor** increments `repositoryCreated` and adds `repository#1` to the trace.
- **`GreetingService`'s constructor** receives the passed `Repository`, increments `serviceCreated`, and records the received dependency's ID. Hence the trace reflects the **observed creation order of the two business beans**, without guessing when Spring creates internal beans.
- Those two beans are **non-lazy** singletons; by the time `refresh()` completes, they have normally been instantiated. `Report` is a prototype and `Audit` is a lazy singleton, so neither is created in this specific case.
- Every `getBean(Report.class)` call requests another `Report`; each instance receives an incrementing ID. We avoid `System.identityHashCode` because its values are not deterministic across runs.
- The `audit` bean has a **definition**, yet creates an instance only when the application calls `getBean(Audit.class)`. If an eager singleton bean later depends on `Audit`, that dependency can cause `Audit` to be created during `refresh()`.
- `@Bean(destroyMethod="shutdown")` tells Spring to call `Repository.shutdown()` during context shutdown. This trace distinguishes a shutdown callback from Java garbage collection.

`@Configuration(proxyBeanMethods = false)` is suitable because the `@Bean` methods **do not call each other directly**; the `Repository` dependency is supplied by the container via parameter. If you called `repository()` directly inside `greetingService()` in this mode, a plain Java call could create a second object, defeating what we want to prove.

## 5. Compile, Run, and Expected Stdout

Open a terminal in **`bean-observation-demo`** containing `pom.xml`. On Windows PowerShell, CMD, Linux, or macOS, the same Maven command applies:

~~~bash
mvn -q clean compile exec:java
~~~

Maven Compiler Plugin invokes `javac` for Java 17, and Exec Maven Plugin runs `demo.BeanObservationDemo` with Spring and transitive dependency JARs on the classpath. Running plain `javac BeanObservationDemo.java` **is not enough** without specifying the Spring classpath.

**Deterministic stdout produced by `System.out.println` statements in Section 4's source**, excluding banners/logs/diagnostics that Maven or a logging backend may print:

~~~text
beforeRefresh.repository=0
beforeRefresh.service=0
afterRefresh.repository=1
afterRefresh.service=1
afterRefresh.report=0
afterRefresh.audit=0
creation.trace=repository#1 > service#1(repository#1)
definition.audit=true
sameService=true
sameInjectedRepository=true
greeting=data:An
report.ids=1,2
sameReport=false
afterLookup.audit=1
sameAuditSingleton=true
destroy.repository#1
context.closed=true
~~~

The `static` counters start at 0 in a **fresh JVM**. If you re-run `main` multiple times in the **same JVM** or make the program multithreaded, counters may differ: this is an observation aid for a single-threaded demo, not a Spring object-identity API.

The output does not rely on wall-clock timing, randomness, memory addresses, or Spring's internal bean order. Because `GreetingService` needs a `Repository` and the trace records only those two business constructors, `repository#1` must be constructed before `service#1(repository#1)` finishes.

## 6. Analyzing Each Piece of Evidence in the Output

| Output Line / Group | What It Proves | What Not to Infer |
| --- | --- | --- |
| `beforeRefresh.*=0` | Configuration source was registered, but the two business beans have not been instantiated yet | Does not mean the container lacks internal bean definitions |
| `afterRefresh.repository=1` and `service=1` | Both non-lazy singletons were instantiated | Does not mean every bean is eager |
| `afterRefresh.report=0` | No prototype instance has been requested yet | Does not mean the `report` bean definition is missing |
| `afterRefresh.audit=0`, `definition.audit=true` | Lazy bean metadata is registered, instance is not created yet | Does not mean `@Lazy` always overrides an eager dependency |
| `creation.trace=repository#1 > service#1(...)` | Before the service constructor completed, Spring supplied the repository | Does not prove an absolute order across all independent singletons |
| `sameService=true` | Two lookups in the same context return the same singleton instance | Not a singleton across the whole JVM or across contexts |
| `sameInjectedRepository=true` | The reference held by the service is the exact `Repository` bean retrieved from context | Does not prove all dependencies share the same scope |
| `report.ids=1,2` and `sameReport=false` | Two requests for a prototype yield two distinct objects | Does not prove the container will destroy them automatically |
| `afterLookup.audit=1` and `sameAuditSingleton=true` | Lazy singleton is created once on demand and reused | Does not mean its scope is prototype |
| `destroy.repository#1` | Shutdown callback executed when closing the context | Does not mean the object was immediately garbage-collected |
| `context.closed=true` | This line ran after the try-with-resources block exited | Not a measurement of how many resources were freed |

### What Is Observed Is *Reference Identity*, Not Just Value

Two distinct objects can have identical fields, identical `toString()`, or `equals()` returning `true`; that does not make them the **same instance**. In this program, `first == second`, `first.repository() == repository`, and `reportA == reportB` test **reference identity**.

Do not use `==` to compare **content equality** of `String` or typical value objects; here `==` is chosen deliberately to prove which bean instances are shared.

## 7. Distinguishing Bean Creation, Dependency Injection, and Business Usage

Observe three related but distinct steps:

1. **Object creation**: `new Repository()` is invoked by the `@Bean repository()` factory method. Spring takes the returned object as the registered bean.
2. **Dependency supply**: the container resolves the `Repository` bean and passes its reference into the `greetingService(Repository repository)` parameter. The factory method forwards that reference to `GreetingService`'s constructor.
3. **Usage**: application code retrieves the service via `getBean`, then calls `first.greet("An")`. Calling business methods is plain Java; Spring does not “re-inject” `Repository` on every `greet` call.

A contrasting design:

~~~java
// Plain Java illustrative snippet, assuming the types exist in the lesson class.
GreetingService wrong = new GreetingService(new Repository());
~~~

That line **manually creates both objects**, without the container resolving or managing them. It can make sense in a tiny plain Java script, but it **does not** prove Spring injected a bean. In this demo, adding that line would also change the counters, so do not insert it into the original program if you want to compare against standard stdout.

### Constructor Injection with Component Scanning

The same DI idea can be written with Spring-managed classes:

~~~java
// Illustrative snippet; classes must be registered/scanned and a Repository bean must exist.
@Component
class GreetingHandler {
    private final Repository repository;

    GreetingHandler(Repository repository) {
        this.repository = repository;
    }
}
~~~

When a component has **a single constructor**, Spring can select that constructor without an explicit `@Autowired`. However, `@Component` does **not** automatically make a class a bean: the context must scan or register the class. The snippet above is **not standalone**; complete runnable code is in Section 4.

DI makes `GreetingService` easy to test with a fake implementation or manually passed dependency, but it does not automatically make code thread-safe or business logic correct.

## 8. Controlled Experiments to Deepen Understanding

Keep the original copy and apply one change at a time, restoring the code before comparing against standard output.

### Experiment A — Created at Refresh or at Lookup?

Mark the `repository()` bean as `@Lazy`:

~~~java
@Bean
@Lazy
public Repository repository() {
    return new Repository();
}
~~~

Even though `Repository` has `@Lazy`, `GreetingService` is still an **eager singleton** and requires a `Repository`. Therefore, the repository can still be instantiated during `refresh()`: a lazy singleton **does not delay a required dependency of an eager singleton**. This is an important counterexample; do not predict `afterRefresh.repository=0` solely from the added annotation.

If you also mark **`GreetingService` as `@Lazy`** and no eager bean depends on either of them, neither is created at refresh. The first lookup of the service triggers Spring to resolve and create the repository followed by the service.

### Experiment B — Singleton vs. Prototype

Change `@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)` on `report()` to the default singleton. Even if no eager bean uses `report`, a standard context pre-instantiates this singleton during refresh, so `afterRefresh.report` becomes `1`, `report.ids` becomes `1,1`, and `sameReport=true`.

If you keep `report` as a prototype and inject it **once into a singleton's constructor**, the singleton normally holds **the same injected prototype instance** for its entire lifetime; Spring does not automatically refresh the dependency on every singleton method call. To create new instances on demand, look into `ObjectProvider<Report>` or lookup-method injection — an advanced topic, not the default behavior of field/constructor injection.

### Experiment C — Does Reordering Registrations Break DI?

Try swapping the positions of `repository()` and `greetingService()` inside `AppConfig`. The bean graph still records the dependency on type `Repository`; Spring does not rely on the author putting factory methods at the top of the file to decide which dependency a service receives. **Do not rely on an absolute creation order among independent singletons** based on source-file order.

### Experiment D — Simulating a Missing Dependency

Temporarily delete or comment out `@Bean repository()` on a copy and re-run. `GreetingService` still requires `Repository`, so the context fails during bootstrap with nested exceptions such as `UnsatisfiedDependencyException`/`NoSuchBeanDefinitionException`. Exact wording and cause ordering may vary across versions; inspect the **root cause** rather than memorizing a fixed stack trace.

### Experiment E — Using Two Containers

Create a second context with the same `AppConfig`. Singletons are shared **within each context**, not across two contexts by default. If you keep the demo's `static` counters, IDs keep incrementing in the same JVM; that is **our own counter**, not Spring assigning global bean IDs.

## 9. Observing in Real Projects: Loggers, Debuggers, and Tests

Counters and `System.out.println` are valuable for learning, while real projects rely on less intrusive observation and targeted tests:

- **Debugger**: set breakpoints in the constructors of `Repository`, `GreetingService`, `report()`, or `audit()`. Inspect the call stack, the `repository` argument, reference identity, and the path leading to bean creation.
- **Logger**: emit structured lifecycle events only when genuinely needed; never log secrets or sensitive data. Avoid letting test logic depend on logging framework initialization order.
- **Identity tests**: use assertions like `assertSame` / `assertNotSame` matching the same reference-checking purpose. If using JUnit, add the dependency and build setup; the current demo **does not require JUnit**.
- **`getBeanDefinitionNames()`**: useful for inspecting registered metadata, though counts and ordering include internal beans and are not guaranteed stable. Do not use “total context bean count” as expected output in this lesson.
- **`BeanPostProcessor`**: lets you observe/hook before and after bean initialization. That is an advanced extension point, **distinct** from `BeanFactoryPostProcessor`, which operates on metadata.
- **Actuator**: meant for Spring Boot apps once the needed dependency and configuration are added. A plain Framework demo does not include Actuator by default.

**Do not measure startup speed by counting constructor log lines.** An application with lazy beans, proxies, or multiple scopes can still initialize cleanly by design. “Bean registered,” “bean instance created,” “dependency injected,” and “business logic executed” are four separate observations.

## 10. Common Misconceptions When Reading Results

| Claim / Mistake | Fact or How to Verify |
| --- | --- |
| “Spring creates all singletons only when `getBean` is called” | Non-lazy singletons are typically instantiated during `ApplicationContext.refresh()` |
| “If a `BeanDefinition` exists, the constructor has definitely run” | Metadata can exist before any instance, especially for lazy/prototype beans |
| “`@Lazy` always prevents a bean from being created at startup” | An eager singleton depending on it can still trigger creation |
| “One Java class can have only one object in Spring” | Multiple definitions, contexts, or scopes can produce multiple instances of the same type |
| “A prototype injected into a singleton recreates itself on every method call” | Injection normally occurs once when the singleton is created |
| “Two beans with equal values share the same reference” | To verify identity, check reference equality (`==`) in the right context |
| “Any object created with `new` is a Spring bean” | An object is a bean only when created/registered through an appropriate container mechanism |
| “A `@Bean` factory method is an instance” | The method declares how to build it; the returned object is the bean instance |
| “`close()` removes objects from the heap immediately” | The context calls eligible destruction callbacks; JVM GC runs independently |
| “Seeing the service creation log proves DI completely succeeded” | Confirm the dependency has the expected reference/type and the service works properly |
| “Beans are always created in source-file declaration order” | The dependency graph, scopes, laziness, and post-processing decide; do not rely on file order |
| “`NoSuchBeanDefinitionException` means Maven is missing Spring JARs” | It usually means a matching bean is missing from the context; distinguish it from compile/classpath errors |

### When Actual Output Differs

1. **Check whether code was modified**: do `@Lazy`, `@Scope`, factory methods, or `getBean` calls differ from the original?
2. **Check fresh JVM vs. same JVM**: `static` counters retain state if `main` is re-run in the same JVM.
3. **Separate logs from application stdout**: Maven, Spring, or logging backends may emit extra diagnostics.
4. **Read the exception chain**: if a dependency is missing or multiple beans share a type, the context can fail right in `refresh()` before printing after-refresh lines.
5. **Check Java and dependencies**: run `mvn -version` and `mvn dependency:tree` to spot runtime/JDK/version conflicts.
6. **Verify via identity**: if `sameInjectedRepository=false`, check whether extra objects were created with `new`, multiple definitions were registered, or unexpected proxies/scopes are active.

## 11. Self-Check Exercises and Official Documentation

Work through each exercise on a clean copy and explain your prediction before running:

1. Point out two lines proving **`Repository` is created before `Service`**, and one line proving `Service` received the exact `Repository` bean from the context.
2. Explain why `reportCreated=0` after refresh yet calling `getBean(Report.class)` twice produces IDs `1,2`.
3. Predict `auditCreated` if `getBean(Audit.class)` is never called anywhere.
4. Change `Report` to singleton; note the exact expected stdout lines that change.
5. Add `@Lazy` to `Repository` and explain why it may still be created during refresh because of `Service`.
6. Add a second `GreetingService` bean of the same type; predict type-lookup behavior and how to fix it with `@Primary`/`@Qualifier`.
7. Manually invoke `new Repository()` and observe the counter incrementing while Spring's `repository` bean **is not replaced**.
8. Keep a reference to `Repository` after `context.close()`. Explain how a shutdown callback differs from garbage collection.
9. Remove the `Repository` definition on a copy and find the root cause exception during refresh; do not treat exact exception message text as a stable API.
10. Run the identity check **without Spring**, passing `Repository` manually into `GreetingService`'s constructor; point out similarities and differences from container-resolved DI.

**Lesson Mastery Checklist:**

- [ ] Distinguish the timing of `register`, `refresh`, singleton creation, prototype retrieval, lazy bean retrieval, and `close()`.
- [ ] Know which bean instance **factory-method parameter injection** supplies to the service.
- [ ] Understand that `sameService=true` and `sameInjectedRepository=true` verify two different relationships.
- [ ] Explain clearly why a **bean definition** does not mean **an object has been created**.
- [ ] Never confuse per-container singletons with JVM-wide singletons.
- [ ] Compile/run Maven on Java 17 and predict all 17 baseline stdout lines accurately.
- [ ] Distinguish observation logging from demo-added observation side effects.

**Official Documentation:**

- [Spring Framework – IoC Container](https://docs.spring.io/spring-framework/reference/core/beans.html)
- [Spring – Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Spring – Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html)
- [Spring – Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html)
- [Spring – Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
- [Spring – Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Spring Framework 7.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes)

**Conclusion:** To know what Spring did, observe at the **right boundaries**: metadata registered, constructors executed, dependency references injected, beans retrieved, and shutdown callbacks invoked. In this demo, counters, creation traces, and reference comparisons provide concrete evidence instead of guessing that “Spring magically created everything.”