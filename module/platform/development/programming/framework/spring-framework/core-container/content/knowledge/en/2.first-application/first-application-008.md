# Comparing a Container-Based Application with Manual Wiring

## 1. One Problem, Two Ways to Build the Object Graph

In Java, one object often needs other objects to complete its work. For example, `GreetingService` needs a `Formatter` to build a greeting and a `ResourceProbe` simulating a resource that must be closed when the application ends.

There are **two valid ways** to build that dependency graph:

1. **Manual wiring:** startup code uses `new` itself, passes objects into constructors, holds references, and closes resources at the right time.
2. **Using Spring IoC Container:** a configuration class declares bean definitions. `ApplicationContext` creates beans, resolves dependency parameters, supplies beans by scope, and invokes appropriate destroy callbacks when the context closes.

The crucial point is that **business logic can stay identical**. The main difference lies in **who is responsible for creating, choosing, connecting, configuring, and managing object lifecycles**, not in the greeting algorithm.

| Question | Manual Wiring | Spring Core Container |
| --- | --- | --- |
| Who creates `Formatter`? | Composition root calls `new VietnameseFormatter()` | Factory method `@Bean formatter()` returns the object |
| Who chooses dependencies for the service? | Caller passes them via constructor | Container resolves parameters of `@Bean greetingService(...)` |
| Who calls the `GreetingService` constructor? | Caller directly | The bean's factory method calls the constructor with Spring-supplied dependencies |
| Who decides instance sharing? | Code retains/reuses references manually | Bean scope; defaults to `singleton` per definition/container |
| Who triggers cleanup? | Caller must do it explicitly | Container calls destroy callbacks of eligible beans on `close()` |
| Is `ApplicationContext` required? | No | Yes, an appropriate context/bean factory implementation |
| Must business logic depend on Spring APIs? | No | **Also no**; the service can remain plain Java |
| Does it automatically make every configuration valid? | No | No; missing/ambiguous dependencies still fail bootstrap |

**Do not equate “manual wiring” with bad design.** Constructor injection is a plain Java technique and is also the foundation Spring uses to inject dependencies. For small programs, manual wiring can be the clearest solution. As the dependency graph, environment configuration, and lifecycles grow complex, a container centralizes those responsibilities.

## 2. Reading the Object Graph and Defining Responsibility Boundaries

Both initialization paths build the **exact same graph shape**:

~~~text
                    GreetingService
                     /           \
                    v             v
               Formatter      ResourceProbe
                    |              |
                    v              v
            VietnameseFormatter  close()

    MANUAL COMPOSITION                SPRING COMPOSITION
    ------------------                ------------------
    new VietnameseFormatter()          @Bean Formatter
    new ResourceProbe()                 @Bean ResourceProbe
    new GreetingService(f, p)           @Bean GreetingService(f, p)
    call p.close()                      context.close()
~~~

`GreetingService` receives only **two references**; it does not need to know whether they came from local variables in `main` or from a container. In this example, it **does not call `new VietnameseFormatter()` inside its constructor**; doing so would lock the service to one implementation and make substituting fakes in tests harder.

The **composition root** is where an application centralizes wiring dependencies (typically in `main`, bootstrap code, or a configuration module). In the manual approach, `main` does it itself; in the Spring approach, `AppConfig` expresses the graph with `@Bean`, while the context orchestrates instantiation and wiring.

**Ownership boundary:** the place that **creates/registers** a resource usually needs to decide where to **close** it. Spring supports scoped callbacks, but cannot automatically clean up arbitrary Java objects created outside the container.

## 3. Pure Java 17 + Spring Framework Project Structure

We place **both approaches inside the same Java file** so differences cannot come from two separate business logic implementations. No Spring Boot, database, component scanning, or HTTP server is required.

Prerequisites: **JDK 17+**, **Maven 3.9+**, and access to Maven Central/mirror for initial dependency downloads. Spring Framework `7.0.9` is used so the version across examples stays consistent.

~~~text
manual-vs-spring-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ManualVsSpringDemo.java
~~~

Create `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>manual-vs-spring-demo</artifactId>
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
                    <mainClass>demo.ManualVsSpringDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` provides `AnnotationConfigApplicationContext`, `@Configuration`, and `@Bean`. Maven resolves the needed Spring dependencies transitively, so you do not have to download individual JARs manually. `maven.compiler.release=17` compiles targeting Java 17 APIs and bytecode.

**Note:** the manual section in this file could run **without a container** by design; however, because the **same file** also holds Spring imports and configuration classes, compiling the demo file still needs `spring-context` on the classpath. To build a program completely free of Spring libraries, move the business interfaces/classes and manual entry point into a plain Java project.

## 4. Complete Code: One Service, Two Composition Roots

Create `src/main/java/demo/ManualVsSpringDemo.java`:

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class ManualVsSpringDemo {

    private ManualVsSpringDemo() {
    }

    // Business contract: imports no Spring APIs at all.
    interface Formatter {
        String format(String name);
    }

    static final class VietnameseFormatter implements Formatter {
        @Override
        public String format(String name) {
            return "Xin chao, " + name;
        }
    }

    // Simulates a resource with a closed state.
    // Not a real network/file connection.
    public static final class ResourceProbe {
        private boolean closed;

        public boolean isClosed() {
            return closed;
        }

        public void close() {
            closed = true;
        }
    }

    static final class GreetingService {
        private final Formatter formatter;
        private final ResourceProbe probe;

        GreetingService(Formatter formatter, ResourceProbe probe) {
            this.formatter = formatter;
            this.probe = probe;
        }

        String greet(String name) {
            return formatter.format(name) + "!";
        }

        boolean hasDependencies(Formatter f, ResourceProbe p) {
            return formatter == f && probe == p;
        }
    }

    // Spring-only composition root.
    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public Formatter formatter() {
            return new VietnameseFormatter();
        }

        @Bean(destroyMethod = "close")
        public ResourceProbe resourceProbe() {
            return new ResourceProbe();
        }

        @Bean
        public GreetingService greetingService(
                Formatter formatter, ResourceProbe resourceProbe) {
            return new GreetingService(formatter, resourceProbe);
        }
    }

    public static void main(String[] args) {
        // ----- 1) Manual wiring -----
        Formatter manualFormatter = new VietnameseFormatter();
        ResourceProbe manualProbe = new ResourceProbe();
        GreetingService manualService =
                new GreetingService(manualFormatter, manualProbe);

        String manualMessage = manualService.greet("Lan");
        System.out.println("manual.message=" + manualMessage);
        System.out.println("manual.wiring="
                + manualService.hasDependencies(manualFormatter, manualProbe));
        System.out.println("manual.closed.before=" + manualProbe.isClosed());

        // The caller owns and closes the resource itself in the manual example.
        manualProbe.close();
        System.out.println("manual.closed.after=" + manualProbe.isClosed());

        // ----- 2) Spring Container wiring -----
        ResourceProbe managedProbe;
        String springMessage;

        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            Formatter managedFormatter = context.getBean(Formatter.class);
            managedProbe = context.getBean(ResourceProbe.class);
            GreetingService managedService =
                    context.getBean(GreetingService.class);

            springMessage = managedService.greet("Lan");
            System.out.println("spring.message=" + springMessage);
            System.out.println("spring.wiring="
                    + managedService.hasDependencies(
                            managedFormatter, managedProbe));
            System.out.println("spring.singleton="
                    + (managedService == context.getBean(GreetingService.class)));
            System.out.println("spring.closed.before=" + managedProbe.isClosed());
        }

        // try-with-resources called context.close(),
        // and Spring invoked destroyMethod="close" on the ResourceProbe bean.
        System.out.println("spring.closed.after=" + managedProbe.isClosed());
        System.out.println("same.business.result="
                + manualMessage.equals(springMessage));
    }
}
~~~

### Why This Comparison Is Fair

1. Both paths use the **same** `GreetingService`, `Formatter`, `VietnameseFormatter`, and `ResourceProbe`. No separate Spring-specific algorithm is written.
2. Manual `main` creates the formatter and probe and passes **those exact two references** to `GreetingService`'s constructor.
3. Spring's `AppConfig` declares three `@Bean` factory methods. When creating `greetingService`, Spring resolves `Formatter` and `ResourceProbe` from the context by type and passes them to the factory method.
4. `@Configuration(proxyBeanMethods = false)` is suitable because `@Bean` methods **do not call each other directly**. Calling `formatter()` directly inside `greetingService()` in this mode could act as a plain Java call and create an extra object outside singleton lookup. The example prevents that mistake by injecting via **factory method parameters**.
5. `GreetingService` and its dependencies use the default `singleton` scope in the current context. Thus two lookups of `GreetingService` return the same reference.
6. Manually, the programmer explicitly calls `manualProbe.close()`. With Spring, `@Bean(destroyMethod="close")` specifies the callback; `try-with-resources` closes the context and Spring runs that callback per singleton lifecycle.

`ResourceProbe` is only a **state-observation instrument** to produce deterministic results. In real applications, objects needing closure may be connection pools, clients, or file handles; closing must follow their specific API and ownership. Never treat a boolean `closed` flag as proof that OS resources were freed.

## 5. Running the Program and Verifying Exact Stdout

In a terminal at `manual-vs-spring-demo` (where `pom.xml` lives), check tool versions:

~~~bash
java -version
javac -version
mvn -version
~~~

Then compile and run:

~~~bash
mvn -q clean compile exec:java
~~~

Maven invokes the compiler targeting Java 17, generates class files, and runs `demo.ManualVsSpringDemo` with a classpath including Spring libraries.

**Exact ten stdout lines printed by `System.out.println` in `main`**, excluding environment-check output, Maven build output, or loggers:

~~~text
manual.message=Xin chao, Lan!
manual.wiring=true
manual.closed.before=false
manual.closed.after=true
spring.message=Xin chao, Lan!
spring.wiring=true
spring.singleton=true
spring.closed.before=false
spring.closed.after=true
same.business.result=true
~~~

### Meaning of Each Line

| Observation | Explanation |
| --- | --- |
| `manual.message` and `spring.message` match | Business behavior **does not change** even though graph construction differs |
| `manual.wiring=true` | Service holds the exact two objects passed by the manual composition root |
| `spring.wiring=true` | Service bean holds the exact two dependency beans retrieved from the same context |
| `spring.singleton=true` | Two `getBean(GreetingService.class)` calls return the **same instance** in the context |
| `manual.closed.before=false` / `after=true` | Manual caller directly invoked `close()` on the probe |
| `spring.closed.before=false` / `after=true` | `ApplicationContext.close()` invoked the registered destroy callback |
| `same.business.result=true` | Both wiring approaches yield the exact same `String` result from the same algorithm |

`==` in `hasDependencies` and `spring.singleton` is used for the right purpose: **comparing reference identity**. `String.equals` is used for the right purpose: **comparing greeting values**. Never use `==` to decide whether two distinct `String` objects have equal content.

**When modifying the code:** if you add a second formatter bean to the context without a disambiguation rule, `getBean(Formatter.class)` or injection can become ambiguous. Then the baseline output **no longer applies**, and the context can fail at startup before printing the Spring section. Do not copy exception message text verbatim, as it can vary across patches.

## 6. Does the Container Replace Constructor Injection?

**No.** Constructor injection is fundamentally a plain Java design technique. The snippet:

~~~java
Formatter f = new VietnameseFormatter();
ResourceProbe p = new ResourceProbe();
GreetingService service = new GreetingService(f, p);
~~~

without Spring is still **manual Dependency Injection**, because dependencies are **passed into** the service rather than looked up or instantiated by the service itself.

Spring DI differs in that **the container resolves** dependencies from bean definitions and scope/qualifier settings, calls appropriate factories/constructors, and manages lifecycles per container contract. In the demo, the method:

~~~java
@Bean
public GreetingService greetingService(
        Formatter formatter, ResourceProbe resourceProbe) {
    return new GreetingService(formatter, resourceProbe);
}
~~~

creates neither `Formatter` nor `ResourceProbe` inside itself. Spring supplies both parameters when instantiating the bean, and Java code uses them normally. The snippets above are **illustrative** and must live inside a class/context with proper imports and types; the standalone compilable program is the full file in Section 4.

Avoid two misconceptions:
- **“With Spring you must never use `new`.”** False. Spring still relies on constructors/factory methods; inside `@Bean`, you can certainly `return new ...`. What matters is that the container registers and manages the **returned object**.
- **“Using `@Autowired` automatically makes business code decoupled.”** Not necessarily. To keep business logic easy to test, keep dependencies explicit via constructors/interfaces and avoid unnecessary global context lookups.

## 7. As the Graph Grows: Where Benefits and Costs Appear

Suppose `GreetingService` is replaced by a system with `OrderService`, `PaymentClient`, `TaxPolicy`, `InventoryRepository`, and `AuditPublisher`.

With manual wiring, you can write a **very explicit** composition root:

~~~java
// Java pseudocode: the classes in this architectural example are not defined yet.
var repository = new InventoryRepository(config);
var taxPolicy = new TaxPolicy(config);
var payment = new PaymentClient(config);
var audit = new AuditPublisher(config);
var orderService = new OrderService(
        repository, taxPolicy, payment, audit);
~~~

Strengths: reading the code shows the exact implementations created, and ordering/ownership is straightforward when well designed; no framework needed. Weaknesses: as configurations, scopes, alternative implementations, environments, and lifecycles multiply, wiring code grows long and can drift across multiple entry points.

With Spring, the composition root is expressed through bean definitions:

~~~java
// Configuration pseudocode: real types and configuration must be defined.
@Configuration(proxyBeanMethods = false)
class OrderConfig {
    @Bean
    OrderService orderService(
            InventoryRepository repository,
            TaxPolicy taxPolicy,
            PaymentClient payment,
            AuditPublisher audit) {
        return new OrderService(repository, taxPolicy, payment, audit);
    }
}
~~~

Strengths: the container manages the graph, resolves dependencies by rule, supports scopes, lifecycle hooks, conditional configuration, and extension points. Weaknesses: **more abstraction**, startup/metadata/proxy overhead, and missing/ambiguous bean errors sometimes appear only at context creation. A broken Spring configuration is not “guessed” and auto-repaired by the container.

**What Spring does not do for you:** write business logic, guarantee thread safety for singletons, resolve all constructor circular dependencies, automatically clean up prototype objects after handing them to callers, or replace unit tests. A container is an object-management tool, not an automatic “architecture fixer.”

## 8. Comparing Lifecycles and Sharing Scopes

### Manual Wiring

- You decide explicitly whether references are shared: passing the same `Formatter` to 5 services or creating 5 distinct formatters is your code's decision.
- A resource created by code must have an owner responsible for cleanup. For resources implementing `AutoCloseable`, `try-with-resources` works as standard Java.
- If the composition root forgets to close an object or double-closes unsafely, Spring cannot automatically fix behavior happening entirely outside the container.

### Container Wiring

- `singleton` is the default scope: typically one instance is shared **per bean definition within each context**.
- `prototype` provides a new instance when requested. Injecting a prototype directly into a singleton's constructor normally resolves that dependency **once when the singleton is created**, rather than swapping objects on every method call.
- Non-`@Lazy` singleton beans in an `ApplicationContext` are typically **instantiated during refresh**, not necessarily delayed until the first `getBean` call.
- On `close()`, Spring invokes destruction callbacks on eligible beans; for prototypes, the container generally **does not manage full destruction callbacks** after handing the instance to the caller.
- If request/session scopes are needed, a matching web context is required; this lesson's console context does not support HTTP request scope out of the box.

**Scope of `ResourceProbe`'s responsibility:** `@Bean(destroyMethod="close")` ensures the callback is registered for that bean and invoked by Spring on normal context closure. It **does not** turn other Java objects you created outside the container into Spring beans, and **does not** guarantee callbacks run if the JVM is forcibly killed.

## 9. Testing: Should You Use Manual Fakes or a Real Context?

One of the best reasons to design services accepting dependencies via constructor is **unit testing without starting Spring**.

Example placed in context with the types from Section 4:

~~~java
Formatter fake = name -> "TEST-" + name;
ResourceProbe probe = new ResourceProbe();
GreetingService service = new GreetingService(fake, probe);

System.out.println(service.greet("Lan"));
probe.close();
~~~

Stdout printed by that illustrative snippet:

~~~text
TEST-Lan!
~~~

`Formatter` is an interface with a single abstract method, so Java 17 allows a lambda. This style of test verifies **service logic** without depending on bean registration, context startup, or auto-configuration. This snippet must be placed in a class/method with access to the nested types; it is **not** a standalone `.java` file.

When should you create a Spring context in a test? When you want to verify **wiring, configuration, bean scopes, lifecycle**, or framework extension points. A context test can catch a missing bean or wrong `@Qualifier` selection that plain Java unit tests do not check.

**Splitting test goals:**
- Plain Java unit tests: algorithm logic, edge cases, fake dependencies, fast execution.
- Context-backed integration tests: configuration graph, DI, proxies/lifecycle, and framework-integrated behavior.
- End-to-end tests: external layers such as HTTP/database/messaging when needed.

Do not boot a context for every unit test just because the project uses Spring. Conversely, do not infer that passing unit tests means Spring configuration is valid: the two test types prove different things.

## 10. Common Mistakes When Comparing the Two Approaches

| Claim / Mistake | Accurate Understanding or Fix |
| --- | --- |
| “Manual wiring is not DI.” | Passing dependencies from caller via constructor **is manual DI** |
| “Spring creates objects without `new`.” | Constructors/factory methods still instantiate Java objects; Spring orchestrates and manages them |
| “The two approaches must use different algorithms.” | **They can use the exact same service class**; only dependency creation/supply changes |
| “`@Bean` on a method works on its own without a context.” | The configuration class must be registered and processed by Spring in a context |
| “`@Component` beans anywhere are automatically scanned.” | Scanning/registration must be configured for the right package |
| “Singleton means one unique object across the JVM.” | Default Spring singletons are scoped per bean definition and container |
| “Spring will always pick the right interface implementation.” | Multiple beans of the same type without `@Qualifier`/`@Primary` cause ambiguity |
| “Calling a `@Bean` method directly always returns the singleton.” | With `proxyBeanMethods=false`, direct calls can instantiate a new object |
| “Using Spring removes the need to manage resources.” | Proper scopes, destroy callbacks, and shutdown are still required; external objects keep their own owner |
| “Use `==` to check whether business strings are equal.” | Use `.equals` for values; `==` here is only for observing references |
| “A prototype changes the dependency inside a singleton on every call.” | Constructor injection normally happens once; use a provider/lookup intentionally if needed |
| “Boot and Core Container are the same thing.” | Spring Boot uses Framework's Core Container, adding conventions and auto-configuration |

### If Output Differs from Expected Stdout

- Check whether you **modified the source** during exercises; the baseline uses three singleton beans in one context.
- If Spring startup throws `NoSuchBeanDefinitionException`/`NoUniqueBeanDefinitionException`, check `@Bean` methods and parameter types; that is a graph/metadata problem, not a Maven error by default.
- If `package org.springframework... does not exist` appears, check the `spring-context` dependency, Maven resolution, and compile classpath.
- If `spring.closed.after=false`, verify `ResourceProbe` is a Spring-managed singleton, `destroyMethod="close"` is set, and the context closed normally. Do not confuse context closure with garbage collection.
- If Maven/logging prints extra lines, compare against the **10 application lines**, not total terminal output.
- If `manual.wiring=false`, check whether an extra dependency was created with `new` between injection and reference comparison.
- If `same.business.result=false`, check whether implementations or inputs still match; different wiring mechanisms **do not force** identical outputs if you configured different dependencies.

## 11. Verifiable Exercises

Perform each exercise individually, then restore the original code to verify against baseline stdout:

1. **Swap implementation:** write `EnglishFormatter` returning `"Hello, " + name`, and swap the implementation in *both* composition roots. Verify `same.business.result` remains `true`.
2. **Swap only one side:** change only the formatter bean in `AppConfig` while keeping the old manual formatter. Predict `same.business.result=false` even though `spring.wiring=true`.
3. **Add a dependency:** create `Clock` (a fake returning a fixed time) and inject it into the service. Compare how many places must change in the manual root vs. `AppConfig`. Avoid reading the system clock directly if you want deterministic expected output.
4. **Change scope:** put `@Scope("prototype")` on the `greetingService` bean, call `getBean` twice, and predict `spring.singleton=false`. Rename the label to `spring.sameInstance` for accuracy.
5. **Missing bean:** temporarily delete `@Bean formatter()` on a copy. The context can fail startup because `GreetingService` cannot resolve its `Formatter` parameter.
6. **Multiple candidates:** add another `Formatter` bean and try `@Primary` or `@Qualifier` to control selection.
7. **Forget cleanup:** remove `manualProbe.close()` and observe `manual.closed.after`. Then restore the code and describe the impact if `ResourceProbe` were a real file/network resource.
8. **Close context:** remove `try-with-resources` on a copy and call `context.close()` explicitly at the right spot; explain exception handling to prevent resource leaks.
9. **Test without Spring:** use the lambda fake in Section 9 to test the service, then explain which tests need a context to verify `@Bean`/lifecycle.
10. **Two contexts:** create two contexts with the same `AppConfig` and compare references of both `GreetingService` beans. Explain why singleton does not mean shared across two contexts.

### Comprehension Checklist

- [ ] State similarities and differences between **manual constructor injection** and **container-managed DI**.
- [ ] Point out the **composition root** in both approaches and where implementation choices are made.
- [ ] Recognize that Spring manages beans **inside the context**, not every object created via `new`.
- [ ] Explain why both `manual.wiring` and `spring.wiring` evaluate to `true`.
- [ ] Distinguish `spring.singleton` from `same.business.result`.
- [ ] Predict all 10 stdout lines accurately when running the unmodified Java file.
- [ ] Know how to close resources by ownership, and choose between context-free unit tests and context-backed wiring tests.

## 12. Summary and References

**Key takeaway:** Spring Core Container does not replace Java design principles. It **replaces the hand-written object-graph wiring and management code** with a centrally configured mechanism providing bean scope rules, dependency resolution, and lifecycle hooks. Both approaches can use constructor injection and keep business classes free of framework dependencies.

- For small graphs, manual wiring is transparent and may be all you need.
- For large graphs with rich configuration and lifecycles, Spring reduces repetitive bootstrap code, while requiring an understanding of bean registration, context, scopes, and error diagnostics.
- Either way, keep dependencies explicit, clarify ownership, test at the right level, and never rely on “container magic” as a substitute for understanding Java.

Official documentation:

- [Spring – Introduction to the IoC Container](https://docs.spring.io/spring-framework/reference/core/beans/introduction.html)
- [Spring – Dependencies and Configuration in Detail](https://docs.spring.io/spring-framework/reference/core/beans/dependencies.html)
- [Spring – Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Spring – Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html)
- [Spring – Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
- [Spring – Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Spring – Bean Lifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Framework 7.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes)

Core exercise: keep `GreetingService` untouched, swap only the **composition root** between `new` and `ApplicationContext`, and measure **results**, **dependency references**, **scope**, and **cleanup**. Once those four factors are clear, you understand the practical difference between a manually wired Java application and one backed by the Spring container.