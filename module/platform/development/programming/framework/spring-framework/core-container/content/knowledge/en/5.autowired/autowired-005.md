# Meaning of `required` and When Dependencies Are Resolved in `@Autowired`

## 1. The Central Question

When the Spring Core Container creates a bean, it may need to look up other beans to inject into a constructor, field, or configuration method. Two things must be distinguished:

1. **Is the dependency mandatory?** The `required` attribute of `@Autowired` affects whether Spring accepts an injection point without a matching dependency.
2. **At what moment does Spring resolve the dependency?** This timing depends on the **bean creation** process, scope, lazy initialization, injection point type, and declared deferral mechanisms — it does not mean resolution happens on every business method call.

General rule:

~~~java
@Autowired
public void configure(Repository repository) {
    this.repository = repository;
}
~~~

`@Autowired` by default is equivalent to `@Autowired(required = true)`. Spring looks up a `Repository` bean satisfying the dependency and invokes the method while configuring the bean. If a required dependency cannot be resolved, bean creation **usually fails**.

Whereas:

~~~java
@Autowired(required = false)
public void setAuditSink(AuditSink auditSink) {
    this.auditSink = auditSink;
}
~~~

allows Spring to **skip calling the setter** if no matching bean exists, letting the object's default state remain in effect. This is an **illustrative** example; the complete Java types and runnable configuration are in section 6.

~~~text
Register BeanDefinition
        |
ApplicationContext.refresh()
        |
        +-- non-lazy singletons: typically created at startup
        |        |
        |        +-- select constructor / resolve constructor args
        |        +-- invoke constructor or factory method
        |        +-- resolve @Autowired fields/methods
        |        +-- run appropriate init callbacks
        |
        +-- lazy singleton: deferred unless required by another eager bean
        |
        +-- prototype: typically created/injected when the container is asked for an instance
        |
getBean(...) -> retrieve managed bean, or trigger creation if not yet created
        |
call business method -> use injected dependency
~~~

This article focuses on Spring Framework 6.x / Java 17+, helping you accurately explain missing-bean errors, avoid confusing `required=false` with arbitrarily passing `null`, and avoid misunderstanding injection timing.

## 2. `required=true`: The Dependency at the Injection Point Is Mandatory

### 2.1. Default Value

Declaring the annotation:

~~~java
@Autowired
private PaymentGateway gateway;
~~~

means Spring must resolve the `PaymentGateway` field when configuring the managed bean. If no matching candidate is found, a missing-dependency error can appear at bean creation time, such as `UnsatisfiedDependencyException` with a missing-bean cause.

Writing:

~~~java
@Autowired(required = true)
private PaymentGateway gateway;
~~~

is equivalent in requirement semantics to omitting the attribute. Both blocks are illustrative only; `PaymentGateway` and the enclosing class must be further defined to compile independently.

**Required** here does not mean "Spring is guaranteed to find a bean", but rather "if the injection condition is not met, the bean being created cannot complete normally". Both bean registration and the ability to select an appropriate candidate are needed.

### 2.2. Having a Bean That Cannot Be Resolved Still Fails

Spring resolves a single dependency by type, and may then consider `@Qualifier`, `@Primary`, parameter name, and other selection rules where appropriate. Common scenarios:

| Scenario | Typical Behavior |
| --- | --- |
| Exactly one matching bean exists | Injects that bean |
| No matching bean, required injection | Bean creation fails |
| Two beans of the same type, no unique disambiguation | May encounter `NoUniqueBeanDefinitionException` |
| Bean to inject exists, but its constructor/factory throws an error | Bean creation fails with the underlying error |
| Bean exists, but does not match the required qualifier | No candidate matches the injection point |
| Unresolvable constructor dependency cycle | Bean graph cannot be constructed completely |

`@Autowired(required=true)` does not automatically resolve situations with multiple candidates or dependency cycles. Those are **bean graph and selection metadata** issues, not a matter of missing text in the annotation.

### 2.3. Errors Can Arrive Before `getBean`

A default `ApplicationContext` typically **pre-instantiates non-lazy singleton beans** during `refresh()`. If bean A has a required `@Autowired` field yet lacks dependency B, the context can fail **right at startup**, before you ever call `context.getBean(A.class)`.

Therefore, the statement "Spring only looks up dependencies when `getBean` is called" is **inaccurate** across all cases. It may hold for a lazy bean not yet requested by another bean, or a prototype requested later, but it is not a universal rule.

## 3. How Does `required=false` Differ on Fields vs Methods?

### 3.1. Optional Field

~~~java
private AuditSink audit = AuditSink.NO_OP;

@Autowired(required = false)
private AuditSink injectedAudit;
~~~

This is **illustrative** only: `AuditSink.NO_OP` is not yet defined. Field `injectedAudit` is allowed to remain uninjected when no candidate exists. If no matching bean exists, Spring typically leaves the field in its **initial default state**; it does not necessarily "call a setter with null", since in this case there is no setter.

If code unconditionally calls `injectedAudit.record(...)` while the field is still null, you can still hit a `NullPointerException`. Marking something optional is a **design decision** that must define behavior when the dependency is absent.

If a safe default is desired, a Null Object can be created:

~~~java
private AuditSink audit = id -> { /* Do nothing */ };

@Autowired(required = false)
public void setAudit(AuditSink audit) {
    this.audit = java.util.Objects.requireNonNull(audit);
}
~~~

When Spring finds no `AuditSink`, the setter does not run and field `audit` keeps its no-op implementation. When a bean exists, the setter replaces the default implementation. In a real project, `AuditSink` must be defined as an appropriate functional interface.

### 3.2. Optional Method: Skipping the **Entire** Call

Suppose:

~~~java
@Autowired(required = false)
public void configureMonitoring(AuditSink audit,
                                MetricSink metrics) {
    this.audit = audit;
    this.metrics = metrics;
    this.monitoringEnabled = true;
}
~~~

This is an illustrative snippet; the main program file in section 6 uses a single-parameter setter for easy observation. With a method taking **two** parameters like the snippet above, `required=false` applies to the **entire injection point**:

- Both matching dependencies exist: Spring can call the method with both.
- One dependency is missing: Spring **skips the entire method**, rather than calling "half the method" or passing `null` into the missing parameter.
- Field `monitoringEnabled` retains its initial default if the method is skipped.

This is one reason not to bundle **independent** options into the same `required=false` method. If audit and metrics can be enabled independently, use two separate optional setters or appropriate `Optional<T>` parameters.

### 3.3. Optional Does **Not** Mean Swallowing Every Error

`required=false` is not an exception handler:

- If a bean candidate exists yet instantiating that bean throws an exception, the error can still prevent the context from creating the bean.
- If an optional method is invoked and its body throws `IllegalArgumentException`, Spring does not ignore that error simply because the annotation is non-required.
- If there are multiple candidates and none can be uniquely chosen, that is a candidate selection error, not a "no bean needed" situation.
- Another dependency outside the optional injection point may still be required.

Thus, do not fix every `UnsatisfiedDependencyException` with `required=false`. Determine whether the dependency can genuinely be absent while the object continues functioning properly.

## 4. `required` on Constructors: Understanding Selection Rules

### 4.1. Only One Constructor: No Need for `@Autowired`

From Spring Framework 4.3 onward, a managed bean class with only **one constructor** typically does not need `@Autowired` written on that constructor:

~~~java
public final class ReportService {
    private final Repository repository;

    public ReportService(Repository repository) {
        this.repository = java.util.Objects.requireNonNull(repository);
    }
}
~~~

This is an illustrative snippet; the `Repository` bean must be available. If Spring directly instantiates `ReportService` from a bean definition, it can pick the single constructor and resolve `Repository`. **Omitting the annotation does not make the dependency optional.**

### 4.2. Multiple Constructors

For a class with multiple constructors, `@Autowired` helps Spring identify candidates. You cannot arbitrarily put `@Autowired(required=true)` on multiple different constructors and expect Spring to choose automatically:

- By default, **only one constructor** in a class may be marked `@Autowired(required=true)`.
- With multiple constructors marked `@Autowired(required=false)`, Spring can evaluate candidates based on argument satisfiability and pick the best-matching constructor per rules.
- If no annotated constructor is satisfied and a no-arg constructor exists, the default constructor can act as a fallback under Spring-supported conditions.
- There are special constructor inference rules for bean definitions and Java records; do not treat "Spring always picks the longest constructor" as a law applying to every class.

**Important:** `@Autowired(required=false)` placed on a constructor does not mean Spring automatically passes null into any missing argument. It affects **how constructor candidates are evaluated**, unlike a non-required setter method being skipped when a dependency is missing.

### 4.3. Required Dependencies Should Be Explicit

If a service needs a repository to operate, use a constructor accepting the repository and do not create a no-arg constructor just to avoid startup errors. An object lacking a required dependency will exist yet may throw errors when business methods run — often even harder to debug.

If a dependency is genuinely optional, consider `Optional<T>`, an appropriate `@Nullable`, a provider, or an optional setter instead of making the class valid in an invariant-violating state.

## 5. Optional **Per Parameter** Instead of the Whole Method

### 5.1. `Optional<T>`

Example:

~~~java
@Autowired
public void configure(Repository repository,
                      java.util.Optional<AuditSink> audit) {
    this.repository = repository;
    this.audit = audit.orElse(null);
}
~~~

This snippet needs matching fields/types if you want to compile it. When `repository` is available but `AuditSink` is not, Spring can pass `Optional.empty()` for the `audit` parameter and **still invoke the method**, unlike `@Autowired(required=false)` applying to the whole multi-parameter method.

| Injection Configuration | Missing audit | Present audit |
| --- | --- | --- |
| `@Autowired(required=false) setAudit(AuditSink)` | Does not call setter | Calls setter |
| `@Autowired(required=false) configure(Repository, AuditSink)` | Skips entire method | Calls if all parameters are satisfied |
| `@Autowired configure(Repository, Optional<AuditSink>)` | Calls with `Optional.empty()` if repo exists | Calls with `Optional.of(bean)` |
| Constructor `Service(Repository, Optional<AuditSink>)` | Constructor can still be called, audit empty | Constructor receives present audit |

`Optional<T>` expresses conditionality **per parameter**, whereas `required` is an attribute **of the injection point annotation**.

### 5.2. `@Nullable`

When a nullability annotation is recognized by Spring in the appropriate version and package, a dependency parameter can be allowed to receive null. **Not every annotation named Nullable from any library is automatically equivalent**; a project must use an annotation supported by Spring 6.x. For beginners, `Optional<T>` often conveys intent more clearly than relying on null.

### 5.3. `ObjectProvider<T>`

If a collaborator needs to be resolved **at processing time**, you can inject Spring's `ObjectProvider<T>` and call `getObject()` or `getIfAvailable()` in appropriate situations:

~~~java
public final class ExportService {
    private final org.springframework.beans.factory.ObjectProvider<Exporter>
            exporters;

    public ExportService(
            org.springframework.beans.factory.ObjectProvider<Exporter>
                    exporters) {
        this.exporters = exporters;
    }

    public void export() {
        Exporter exporter = exporters.getIfAvailable();
        if (exporter != null) {
            exporter.run();
        }
    }
}
~~~

This is an **illustrative** snippet without `Exporter` defined. `ObjectProvider` allows deferring **a specific lookup**, though it does not exempt errors caused by multiple ambiguous candidates or a failing candidate factory. With prototype scope, looking up from the provider can create a new instance per request.

If business logic needs complete independence from Spring, an injected `ExporterFactory` or `Supplier<Exporter>` interface often keeps dependency boundaries cleaner.

## 6. Spring Framework 6.2 / Java 17 Example: Observing `required` and Timing

A complete console program using two independent contexts:

- **First context** has `TicketStore` but **no `AuditSink`**. The service has a required `TicketStore` constructor and an `@Autowired(required=false)` setter for audit; the setter is skipped. A `@Lazy` singleton is not yet created after refresh; when `getBean(LazySummary.class)` is called, Spring creates it.
- **Second context** has both `TicketStore` and `AuditSink`. The audit setter is invoked during service creation, and the business method records an audit before returning the result.

The application uses no Spring Boot, HTTP server, database, or AOP. It demonstrates **observable moments**, without promising that unrelated singletons initialize in source-code order.

### 6.1. Requirements and Directory Structure

Requires **JDK 17+** and Apache Maven. Maven may download dependencies on the first run.

~~~text
required-timing-demo/
├── pom.xml
└── src/main/java/demo/RequiredTimingDemo.java
~~~

Create `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>required-timing-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
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
                    <mainClass>demo.RequiredTimingDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.2. Complete Java File

Create `src/main/java/demo/RequiredTimingDemo.java`:

~~~java
package demo;

import java.util.Objects;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Lazy;

public final class RequiredTimingDemo {
    private RequiredTimingDemo() {}

    public interface TicketStore {
        String find(String id);
    }

    public static final class MemoryTicketStore implements TicketStore {
        @Override
        public String find(String id) {
            return "TICKET(" + id + ")";
        }
    }

    public interface AuditSink {
        void record(String id);
    }

    public static final class ConsoleAuditSink implements AuditSink {
        @Override
        public void record(String id) {
            System.out.println("AUDIT " + id);
        }
    }

    public static final class TicketService {
        private final TicketStore store;  // Required
        private AuditSink audit;          // Optional
        private boolean auditSetterCalled;

        public TicketService(TicketStore store) {
            this.store = Objects.requireNonNull(store, "store");
        }

        @Autowired(required = false)
        public void setAudit(AuditSink audit) {
            this.audit = Objects.requireNonNull(audit, "audit");
            this.auditSetterCalled = true;
        }

        public boolean auditConfigured() {
            return auditSetterCalled;
        }

        public String process(String id) {
            String ticket = store.find(id);
            if (audit != null) {
                audit.record(id);
            }
            return "DONE " + ticket;
        }
    }

    public static final class LazySummary {
        private final TicketStore store;

        public LazySummary(TicketStore store) {
            this.store = Objects.requireNonNull(store);
        }

        public String summarize(String id) {
            return "SUMMARY " + store.find(id);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class CoreConfig {
        @Bean
        public TicketStore ticketStore() {
            return new MemoryTicketStore();
        }

        @Bean
        public TicketService ticketService(TicketStore store) {
            return new TicketService(store);
        }

        @Bean
        @Lazy
        public LazySummary lazySummary(TicketStore store) {
            System.out.println("CREATE lazy-summary");
            return new LazySummary(store);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @Import(CoreConfig.class)
    public static class WithAuditConfig {
        @Bean
        public AuditSink auditSink() {
            return new ConsoleAuditSink();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(CoreConfig.class)) {
            System.out.println("-- without audit --");
            System.out.println("LAZY_READY "
                    + context.getBeanFactory()
                             .containsSingleton("lazySummary"));

            TicketService service = context.getBean(TicketService.class);
            System.out.println("AUDIT_SET " + service.auditConfigured());
            System.out.println("RESULT " + service.process("A1"));

            LazySummary lazy = context.getBean(LazySummary.class);
            System.out.println(lazy.summarize("A1"));
            System.out.println("LAZY_READY "
                    + context.getBeanFactory()
                             .containsSingleton("lazySummary"));
        }

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             WithAuditConfig.class)) {
            System.out.println("-- with audit --");
            TicketService service = context.getBean(TicketService.class);
            System.out.println("AUDIT_SET " + service.auditConfigured());
            System.out.println("RESULT " + service.process("B2"));
        }
    }
}
~~~

There is no `@Autowired` on `TicketService`'s constructor because it has only one constructor, yet the program also uses **`@Bean ticketService(TicketStore)`**: Spring itself injects the parameter into the factory method; the factory body calls the Java constructor. That still provides a required dependency, though it should not be confused with Spring directly inferring the service class's constructor.

### 6.3. Compile, Run, and Stdout

Open a terminal in the `required-timing-demo` directory:

~~~bash
mvn -version
mvn -q compile exec:java
~~~

**Lines printed by the program via `System.out.println` in exact order:**

~~~text
-- without audit --
LAZY_READY false
AUDIT_SET false
RESULT DONE TICKET(A1)
CREATE lazy-summary
SUMMARY TICKET(A1)
LAZY_READY true
-- with audit --
AUDIT_SET true
AUDIT B2
RESULT DONE TICKET(B2)
~~~

`mvn -version` prints Maven/JDK versions; Maven and Spring may also emit other logs depending on the environment. The block above records only the lines **intentionally printed by Java code**, without claiming the entire terminal consists solely of those lines.

### 6.4. Tracing When Spring Resolves Dependencies

**Context without audit:**

1. `AnnotationConfigApplicationContext(CoreConfig.class)` registers the config and **refreshes** the context. Non-lazy singletons, including `TicketStore` and `TicketService`, have typically been created before this constructor returns.
2. When creating `ticketService`, Spring must resolve the `TicketStore` parameter of the `@Bean` factory method. This is a **required** dependency; if missing, startup cannot complete as in the demo.
3. The `TicketService` bean is created, then Spring processes the `@Autowired(required=false)` setter. Without an `AuditSink` bean, the setter **is not called**, and the `auditSetterCalled` flag remains `false`.
4. The `LazySummary` bean is declared `@Lazy` and not required by another eager bean; after refresh, `containsSingleton("lazySummary")` is `false`.
5. `getBean(TicketService.class)` returns the configured service. `process("A1")` simply uses the already-injected dependency and does not cause Spring to re-run the setter. It prints `RESULT DONE TICKET(A1)`.
6. When `getBean(LazySummary.class)` is called, Spring must instantiate the lazy bean. The factory method prints `CREATE lazy-summary`, then Spring returns the object. `summarize("A1")` returns `SUMMARY TICKET(A1)`.
7. From this point, the `lazySummary` singleton exists, so `containsSingleton("lazySummary")` returns `true`.

**Context with audit:**

1. `WithAuditConfig` imports `CoreConfig` and registers an additional `AuditSink` bean. Spring can resolve both repository and audit when configuring `TicketService`.
2. Setter `setAudit(AuditSink)` is invoked during bean creation; `auditSetterCalled` becomes `true` **before** `main` calls `getBean(TicketService.class)`.
3. `process("B2")` calls `audit.record("B2")`, prints `AUDIT B2`, then returns `DONE TICKET(B2)` for `main` to print.
4. Each context has its own set of singletons. Do not infer from two runs that Spring keeps one global singleton across the entire JVM.

**There is no stdout about when `ticketStore`/`ticketService` were created**, because their constructors/factories print nothing. Thus the output is deterministic and does not depend on the order in which Spring creates unrelated singletons.

## 7. Eager, Lazy, Prototype: "When" Depends on Bean Type

| Bean Kind | When Spring Typically Creates and Resolves Dependencies |
| --- | --- |
| Non-lazy singleton | During ApplicationContext refresh/pre-instantiation (unless other conditions defer it) |
| `@Lazy` singleton | First time requested, unless another eager dependency forces earlier creation |
| Prototype | Each time the container is asked for a prototype instance, per scope mechanism |
| Request/session scoped | When a valid web scope has a corresponding request; requires a web-aware context |
| Bean created via `new` outside Spring | Spring does not automatically process `@Autowired` on that instance |
| `ObjectProvider<T>` injection | Provider can be supplied upfront; target dependency is looked up when provider is used |
| Proxy from `@Lazy` at injection point | Proxy can be injected upfront; target is looked up when the proxy needs to resolve target |

### 7.1. `@Lazy` on a Bean Definition Can Be Woken Up by an Eager Dependency

Example:

~~~java
@Bean
@Lazy
ExternalClient externalClient() {
    return new ExternalClient();
}

@Bean
EagerService eagerService(ExternalClient client) {
    return new EagerService(client);
}
~~~

This is **illustrative**; `ExternalClient` and `EagerService` must be defined. If Spring needs to create `eagerService` at startup, it must resolve the `client` parameter. Result: **`externalClient` can be created during startup despite `@Lazy`**.

Therefore, the claim "every bean marked lazy is only created on the first `getBean` for that bean name" is false.

### 7.2. `@Lazy` at an Injection Point Can Create a Proxy

In scenarios supported by Spring, placing `@Lazy` at a parameter/field injection point can create a **resolution-deferring proxy**:

~~~java
public EagerService(@Lazy ExternalClient client) {
    this.client = client;
}
~~~

This is an illustrative snippet. The injected object may be a proxy, while finding and creating the real target can be deferred until first use. However:

- Not every class/method can be proxied identically (especially `final` classes/methods and proxy mode choices).
- A missing-bean error can be deferred until runtime use of the proxy.
- Do not confuse "the constructor received a proxy" with "the constructor actually received no dependency".
- Do not indiscriminately mark all injection points lazy to mask dependency cycles.

### 7.3. Prototype Injected into a Singleton

If a prototype bean is injected **directly** into a singleton via constructor, obtaining the prototype usually happens **when the singleton is created**. The singleton holds onto that reference; it **does not automatically receive a new prototype every time a business method runs**.

To obtain a prototype instance per task, use `ObjectProvider<T>`, an appropriate scoped proxy, or an injected factory with a clear contract. Prototypes also have different cleanup lifecycles than singletons: Spring does not automatically run all destruction callbacks on context close for every prototype instance dispensed.

### 7.4. When Does "Dependency Has Been Resolved" Actually Happen?

Four moments can be separated:

1. **Bean definition registration**: Spring learns which beans and metadata exist. This does not mean objects exist yet.
2. **Instance creation**: selects constructor/factory, resolves dependencies needed immediately to invoke constructor/factory.
3. **Property population/injection**: processes `@Autowired` fields and methods, property values, and related lifecycle steps.
4. **Business method execution**: caller invokes behavior on a ready object. Fixed dependencies are typically just **used**, not automatically looked up again.

Features like proxies, providers, and prototype factories can alter or defer part of resolution, yet should be treated as **explicit configurations**, without invalidating the default rules.

## 8. A Plain Java 17 Example Distinguishing Injection from Dynamic Lookup

You do not need Spring to see that a dependency supplied via constructor is retained in a field.

Create `PlainRequiredDemo.java` in a standalone working directory:

~~~java
import java.util.Objects;
import java.util.function.Supplier;

public class PlainRequiredDemo {
    interface Formatter {
        String format(String value);
    }

    static class Service {
        private final Formatter formatter;

        Service(Formatter formatter) {
            this.formatter = Objects.requireNonNull(formatter);
        }

        String run(String value) {
            return formatter.format(value);
        }
    }

    static class DynamicService {
        private final Supplier<Formatter> provider;

        DynamicService(Supplier<Formatter> provider) {
            this.provider = Objects.requireNonNull(provider);
        }

        String run(String value) {
            return provider.get().format(value);
        }
    }

    public static void main(String[] args) {
        Formatter fixed = value -> "FIXED:" + value;
        Service service = new Service(fixed);
        System.out.println(service.run("A"));
        System.out.println(service.run("B"));

        int[] calls = {0};
        DynamicService dynamic = new DynamicService(() -> {
            calls[0]++;
            return value -> "DYNAMIC:" + value;
        });
        System.out.println(dynamic.run("C"));
        System.out.println(dynamic.run("D"));
        System.out.println("LOOKUPS " + calls[0]);
    }
}
~~~

Compile and run with **JDK 17+** (no Spring required):

~~~bash
javac --release 17 -encoding UTF-8 PlainRequiredDemo.java
java PlainRequiredDemo
~~~

Exact stdout:

~~~text
FIXED:A
FIXED:B
DYNAMIC:C
DYNAMIC:D
LOOKUPS 2
~~~

In `Service`, the `fixed` dependency was passed into the constructor once. Two calls to `run` **do not re-invoke the formatter supplier**. In contrast, `DynamicService` calls `provider.get()` on every `run`, because our code **explicitly designed** it that way.

This is a pure Java analog helping understand `ObjectProvider` or factory abstractions in Spring: on-demand lookup is an API choice, **not the default for every method invocation on a managed bean**.

## 9. Handling Missing Beans Properly Without Masking Problems

### 9.1. Genuinely Required Dependencies

Suppose `TicketService` cannot work without `TicketStore`. Let the constructor or `@Bean` factory method require that bean. If absent, early startup failure for eager singletons is a misconfiguration signal to fix.

Do not switch to:

~~~java
@Autowired(required = false)
public void setStore(TicketStore store) {
    this.store = store;
}
~~~

and then call `store.find(...)` unconditionally if the setter never ran. That merely **defers the failure** to business execution time rather than solving the required dependency.

### 9.2. Genuinely Optional Dependencies

Audit, telemetry, tracing, or an auxiliary cache optimization may not affect core functionality. Optional setters, `Optional<T>`, or Null Object defaults can be used, provided:

- Tests exist for when the dependency is present.
- Tests exist for when the dependency is absent.
- Fallback behavior is clearly documented.
- Legal/security requirements that actually mandate auditing are not bypassed.

`TicketService` in the demo illustrates continuing to process when `AuditSink` is absent, without a `NullPointerException`.

### 9.3. Two Beans of the Same Type Are Not "Optional"

If two `AuditSink` beans are registered under the same interface without a unique selection rule, the outcome does not become "no audit". Intentional selection is needed: `@Primary`, `@Qualifier`, collection injection, or a runtime-data strategy/router.

### 9.4. Lazy Errors Happening Late Are Still Configuration Errors

A bean marked `@Lazy` may let startup succeed while a missing-dependency error only surfaces on the first `getBean`. That does not mean `required=true` was disabled; **the mandatory condition is simply checked when the bean is actually created**.

Have integration tests or appropriate startup checks if you want early verification of critical object graphs.

## 10. Relationship with `@Bean` Factory Methods and XML

### 10.1. Factory Method Parameters Are Resolved by Spring

~~~java
@Bean
TicketService ticketService(TicketStore store) {
    return new TicketService(store);
}
~~~

This is an excerpt from the runnable program. Spring identifies the `@Bean` method as a bean factory method and automatically resolves the `TicketStore` parameter. There is no need to place `@Autowired` on the `@Bean` method itself just for it to receive parameters.

For the `TicketService` class returned by the method, the `@Autowired(required=false)` setter is still inspected by the bean post-processor because it is a Spring-managed bean.

**Must separate:** resolution of factory parameters happens **before** invoking the factory; injection of setters/fields on the product happens **after** the product is created and before the bean is used normally.

### 10.2. XML Bean Dependencies

An XML configuration can declare a constructor dependency:

~~~xml
<bean id="ticketStore" class="demo.MemoryTicketStore"/>

<bean id="ticketService" class="demo.TicketService">
    <constructor-arg ref="ticketStore"/>
</bean>
~~~

This is **illustrative**; the Java classes in the Maven program are nested classes inside `demo.RequiredTimingDemo`, so the name `demo.MemoryTicketStore` from this snippet cannot be used directly. In a real project, use proper fully qualified class names or extract top-level classes.

`<constructor-arg ref="ticketStore"/>` is a required reference per metadata: if the referenced bean name does not exist, bean creation fails. There is no `required=false` attribute on every `<constructor-arg>` with identical semantics to `@Autowired(required=false)`; do not try to translate one-to-one.

## 11. Common Misconceptions

| Misconception | Truth |
| --- | --- |
| "Without writing `required`, the dependency is optional." | Default is `@Autowired(required=true)`. |
| "`required=false` will call the setter with `null`." | For a non-required method missing a dependency, Spring may **skip calling the method**. |
| "`required=false` also handles a candidate bean that fails to instantiate." | No: factory/constructor errors can still break bean creation. |
| "Every optional field has a valid value if uninjected." | It keeps its default, which may be null; the object needs a safe fallback. |
| "Constructor `required=false` works just like setter `required=false`." | Constructor resolution and method injection have different rules. |
| "One constructor without `@Autowired` means no DI." | A managed bean with one constructor can still be injected automatically. |
| "Spring resolves dependencies on every business method call." | Typically resolution/injection occurs when the bean is created; methods simply use existing dependencies. |
| "Dependencies are only looked up at `getBean`." | Eager singletons are typically created during context refresh. |
| "`@Lazy` strictly prevents a bean from being created at startup." | An eager dependency can force a lazy bean to initialize early. |
| "`@Lazy` on a field is identical to `@Lazy` on a bean definition." | Placement can create a lazy proxy with different resolution timing. |
| "Injecting a prototype into a singleton gives a new prototype per request." | The singleton usually holds one instance injected at creation. |
| "`@Autowired` on a manually `new`'d class will be executed by the JVM." | No, it requires Spring-managed lifecycle/processors. |
| "`@Primary` fixes missing beans." | Primary breaks ties among multiple beans; it does not create a missing bean. |
| "All singleton beans are created in source declaration order." | Do not rely on source order; rely only on dependency/lifecycle semantics. |
| "Successful context refresh proves every lazy bean is valid." | Lazy beans may only be created/validated when requested. |
| "`ObjectProvider` always returns a bean or null, never errors." | It still follows missing/multiple candidate and bean-creation error rules. |

## 12. Exercises with Answers

**Exercise 1.** Is `@Autowired` without `required` true or false?

**Answer:** Default **true**. The dependency at the injection point must be satisfied unless another supported form of optionality is used.

**Exercise 2.** Method `@Autowired(required=false) void configure(Audit a, Metrics m)` has audit but lacks metrics. Will it be called with metrics as null?

**Answer:** No under non-required method semantics: Spring may skip **the entire method**. If audit and metrics need separate optionality, split injection points or use `Optional<T>`.

**Exercise 3.** An eager singleton bean lacks required `TicketStore`. Does the error happen on the first `getBean(TicketService.class)`?

**Answer:** It can happen **immediately during `ApplicationContext.refresh()`** creating non-lazy singletons, before the application's `getBean` call.

**Exercise 4.** A `@Lazy` bean is not required by any eager dependency. When are its dependencies resolved?

**Answer:** Typically when the bean is first requested for creation. If that bean is injected into an eager singleton in a way needing the target instantiated, timing can be earlier.

**Exercise 5.** A singleton has a prototype injected directly. Does the second method call on the singleton automatically get a second prototype?

**Answer:** Not by default. The singleton holds the prototype reference injected at creation. To get new instances, use a provider/factory or appropriate scoping approach.

**Exercise 6.** There are two `AuditSink` candidates; does a `required=false` setter method pick one automatically or skip?

**Answer:** Neither should be assumed. This is an ambiguity resolution issue; it requires qualifier/primary or an appropriate multi-bean injection design.

**Exercise 7.** In the program, why is there `LAZY_READY false`, then `CREATE lazy-summary`, and then `LAZY_READY true`?

**Answer:** `LazySummary` is a `@Lazy` singleton not requested at refresh. `getBean(LazySummary.class)` triggers the factory method to create the instance; afterward the instance resides in the singleton registry.

**Exercise 8.** Why does `AUDIT B2` appear before `RESULT DONE TICKET(B2)`?

**Answer:** `TicketService.process` invokes `audit.record` before returning the string; `main` prints the result after the call finishes.

**Exercise 9.** Should `required=false` be used for a repository the service cannot function without?

**Answer:** No. That hides a mandatory dependency, potentially turning an obvious startup error into a hard-to-trace runtime failure.

**Exercise 10.** Does `@Bean TicketService ticketService(TicketStore store)` need `@Autowired` on the method for Spring to inject `store`?

**Answer:** No. Spring recognizes and resolves factory method parameters from `@Bean` metadata.

## 13. Implementation and Verification Checklist

- [ ] Know `@Autowired` defaults to `required=true`.
- [ ] Classify collaborators: mandatory vs genuinely optional, not choosing based on "don't fail startup".
- [ ] Use constructor/factory method parameters for mandatory dependencies.
- [ ] When using `@Autowired(required=false)` on a method, clearly design behavior if the method is skipped.
- [ ] Do not confuse optional injection with Spring always passing `null`.
- [ ] For multi-argument methods, remember the all-or-nothing nature of method resolution.
- [ ] Use `Optional<T>` or a provider when per-parameter/on-demand optionality is needed.
- [ ] With multiple beans of the same type, have a proper selection rule: qualifier, primary, or aggregate injection.
- [ ] Do not apply method `required=false` semantics verbatim to constructor selection.
- [ ] Determine whether a bean is created at startup (non-lazy singleton) or later (lazy/prototype).
- [ ] Check for lazy beans required by another eager dependency.
- [ ] Do not expect Spring to re-run setters every time a business method is invoked.
- [ ] Do not expect `@Autowired` fields to run automatically on manually `new`'d objects.
- [ ] With prototypes directly inside singletons, decide whether a provider/factory is needed for fresh instances.
- [ ] Test missing-bean, single-bean, and multi-bean scenarios when configuration matters.
- [ ] Read the root cause of `BeanCreationException`/`UnsatisfiedDependencyException`.
- [ ] Close the context when done and avoid calling managed resources after closing.
- [ ] Ensure Java 17 build and distinguish program stdout lines from Maven logs.

### Official Spring Documentation References

- [`@Autowired` — constructor, fields, methods, required semantics](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [Lazy-initialized beans](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html)
- [Bean scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [`@Bean` factory methods](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)

**Conclusion:** `required` answers "can this injection point tolerate an absent dependency?", whereas **resolution timing** depends on how and when Spring creates the bean. For eager singletons, required dependency errors can appear immediately at refresh; for lazy/prototype beans, errors can surface later; with proxies/providers, target lookup can be deferred further. Understanding these two axes lets you design dependencies properly, predict errors accurately, and avoid abusing `required=false` to mask missing configuration.