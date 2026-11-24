# Multi-Argument Configuration Method Injection in Spring Core Container

## 1. Lesson Objective

A bean often needs **multiple collaborators** at once: for instance, a repository to read data, a formatter to format output, an audit sink for audit logs, and a metrics sink for metrics. Spring Core Container can automatically find the right beans and **pass each argument** into a configuration method annotated with `@Autowired`.

Notably, such a method:

- **Does not have to be named `set...`** like a JavaBeans setter. It can be named `configure`, `prepare`, or `attachInfrastructure`.
- Can accept **multiple parameters of different types** in a single call.
- Is invoked by Spring during **bean configuration**, not every time the application invokes a business operation.
- Defaults to `required=true`; with `required=false` on the method, Spring may **skip the entire method** if a needed dependency does not exist.
- Differs from `@Bean`: a `@Bean` method is a **factory method that creates/publishes a bean**, whereas a regular `@Autowired` method **configures an already created bean**.

This lesson covers the mechanism, multi-argument cases, bean selection, the difference between required and optional dependencies, and a standalone Spring Framework 6.2 + Java 17 example with exact Maven commands and stdout.

~~~text
ApplicationContext
    |
    | (1) call multi-argument factory method
    |     @Bean OrderEngine orderEngine(
    |           Repository repository,
    |           Formatter formatter,
    |           @Value(...) String label)
    v
 OrderEngine instance (already has repository, formatter, label)
    |
    | (2) BeanPostProcessor processes @Autowired
    |     configureExtras(AuditSink audit, MetricSink metrics)
    |            |
    |            +-- both available -> invoke method once
    |            +-- one missing, required=false -> skip method
    |
    v
 bean ready for use -> execute(orderId)
~~~

Therefore, distinguish **object instantiation**, **parameter injection for configuration**, and **business method execution**. These are three separate phases.

## 2. `@Autowired` on an Arbitrary Multi-Argument Method

### 2.1. Basic Syntax

~~~java
public final class ReportService {
    private Formatter formatter;
    private AuditSink auditSink;

    @Autowired
    public void configure(Formatter formatter, AuditSink auditSink) {
        this.formatter = formatter;
        this.auditSink = auditSink;
    }
}
~~~

This is **illustrative code**, not standalone runnable, because `Formatter`, `AuditSink`, and the `@Autowired` import are not included in this block. Key semantics:

1. Spring instantiates a `ReportService` from its bean definition.
2. `AutowiredAnnotationBeanPostProcessor` detects the `configure` method.
3. Spring resolves **each parameter** by metadata/type and any applicable qualifiers.
4. Once the required dependencies are satisfied, the container calls `configure(formatterBean, auditBean)` to set state.
5. The bean proceeds through remaining initialization/lifecycle steps before entering normal use.

Since the method only configures the object, it typically uses a `void` return type. It may declare appropriate visibility—it does not have to be public—though `static` methods and hard-to-control reflection/access tricks should be avoided for this purpose.

**Do not confuse this with per-call invocation:** Spring **does not** re-invoke `configure` before every `service.generate()` call. For a standard singleton bean, configuration injection completes once during bean creation. For a prototype, each newly created object runs its own configuration phase.

### 2.2. Setter Injection Is a Special Case of Method Injection

The familiar setter:

~~~java
@Autowired
public void setFormatter(Formatter formatter) {
    this.formatter = formatter;
}
~~~

is simply **single-parameter method injection** following the JavaBeans naming convention. Method injection can accept multiple parameters:

~~~java
@Autowired
public void configure(Formatter formatter,
                      AuditSink auditSink,
                      MetricsSink metricsSink) {
    this.formatter = formatter;
    this.auditSink = auditSink;
    this.metricsSink = metricsSink;
}
~~~

The name `configure` breaks no `@Autowired` rules; the annotation tells Spring it is an injection point. The code in both blocks is purely for structural comparison; interfaces and fields must be defined in a real project.

A multi-argument method is fitting when the dependencies **together form a meaningful configuration step**, such as a group of components that belong attached together. Do not lump unrelated collaborators into one method just to reduce setter count or mask single-responsibility issues.

## 3. Required Semantics: A Multi-Argument Method Is a Single Injection Point

### 3.1. `@Autowired` Requires Dependencies by Default

~~~java
@Autowired
public void configure(Repository repository,
                      Formatter formatter) {
    this.repository = repository;
    this.formatter = formatter;
}
~~~

The default is `required=true`. When Spring cannot locate one of the needed parameters, bean creation generally fails with a dependency error; it does not call the method with an arbitrary argument or silently skip required injection.

Errors to distinguish:

- **No matching candidate**: typically triggers `UnsatisfiedDependencyException` with a cause related to `NoSuchBeanDefinitionException`.
- **Multiple beans of the same type with no disambiguation**: usually caused by `NoUniqueBeanDefinitionException` in the cause chain.
- **Candidate bean exists, yet its own constructor/factory fails**: still causes bean creation to fail.
- **Method body throws an exception when invoked**: not a “missing dependency” error; Spring may wrap it as a bean creation failure.

Inspect the root cause in the stack trace rather than altering configuration based solely on the outermost exception name.

### 3.2. `@Autowired(required = false)`: Skipping the Whole Method

~~~java
@Autowired(required = false)
public void configureExtras(AuditSink audit,
                            MetricSink metrics) {
    this.audit = audit;
    this.metrics = metrics;
    this.extrasConfigured = true;
}
~~~

This is an **illustrative excerpt**, taken from the complete program in section 6. Crucial rule:

- If **both** beans exist, Spring invokes the method and passes both arguments.
- If **`MetricSink` is missing** while `AuditSink` exists, Spring **does not call `configureExtras`** and does not “half-call the method” with `null`.
- If neither exists, the method is likewise skipped.
- Initial fields retain the object's defaults, e.g., `extrasConfigured=false`.
- `required=false` **does not** resolve ambiguity caused by two `MetricSink` candidate beans, nor does it swallow bean initialization failures.

Treat this pair of dependencies as **an atomic optional configuration point** (*all-or-nothing*). If you want auditing to work even when metrics are absent, **do not** place both into one non-required method expecting audit to wire itself; adjust the injection design.

| Context | `AuditSink` | `MetricSink` | `configureExtras` with `required=false` |
| --- | --- | --- | --- |
| Complete | Present | Present | Invoked, attaches both |
| Missing metrics | Present | Absent | Completely skipped |
| Missing audit | Absent | Present | Completely skipped |
| Missing both | Absent | Absent | Completely skipped |

This table assumes each type has at most one matching bean and no other errors; it makes no promise about disambiguating multiple candidates.

### 3.3. When Multiple Options Are Independent, Split Methods

Example:

~~~java
@Autowired(required = false)
public void setAuditSink(AuditSink sink) {
    this.auditSink = sink;
}

@Autowired(required = false)
public void setMetricSink(MetricSink sink) {
    this.metricSink = sink;
}
~~~

Two independent injection points: if only audit exists, the audit setter still runs; missing metrics only skips the metric setter. This suits capabilities that genuinely do not depend on each other.

Conversely, if two dependencies must be installed together to preserve an invariant, a single `configureExtras(audit, metrics)` method is intentional—provided there is a **fallback behavior** when the method is skipped.

## 4. Per-Parameter Optionality: `Optional<T>`, `@Nullable`, and Providers

### 4.1. A Method Still Runs When an Individual Parameter Is Optional

~~~java
@Autowired
public void configure(AuditSink audit,
                      java.util.Optional<MetricSink> metrics) {
    this.audit = audit;
    this.metricsEnabled = metrics.isPresent();
}
~~~

Spring supports `Optional<MetricSink>` as an optional injection point. When `AuditSink` is present and `MetricSink` is missing, the method **still runs**, receiving `Optional.empty()` for the metrics parameter. By contrast, if **`AuditSink` itself** is missing, the method fails its requirement because that parameter is required.

This is a major difference from method-level `@Autowired(required=false)`:

| State | `required=false` method with 2 regular params | `@Autowired` method with `AuditSink, Optional<MetricSink>` |
| --- | --- | --- |
| Both audit and metrics | Invoked | Invoked, `Optional` holds metrics |
| Audit present, metrics missing | Skips entire method | Invoked, `Optional.empty()` |
| Audit missing, metrics present | Skips entire method | Fails required dependency for audit |

This pattern is demonstrated on an `OptionalObserver` bean in the runnable program in section 6 so you can compare results side by side.

### 4.2. `@Nullable` and `ObjectProvider<T>`

In some Spring versions, you can annotate a parameter as nullable with a Spring-supported annotation to express optionality. In Spring Framework 6.x, choose the nullability annotation appropriate to your actual module/version rather than placing an arbitrary annotation and expecting Spring to recognize it.

`ObjectProvider<MetricSink>` is another option if you **want to look up the dependency on demand**, instead of locking in a reference during configuration:

~~~java
@Autowired
public void configure(ObjectProvider<MetricSink> metricsProvider) {
    this.metricsProvider = metricsProvider;
}
~~~

This is an illustrative snippet needing `org.springframework.beans.factory.ObjectProvider` and the matching field. Code can call `metricsProvider.getIfAvailable()` at processing time to request the bean if present. With multiple candidates, resolution rules apply; a provider does not conjure a “right” candidate when configuration is ambiguous.

Use `Optional<T>` when you only need a present/absent decision at configuration time. Use a provider when you need on-demand lookup, prototypes, or deliberate dynamic lookup; avoid complex abstractions when a stable parameter suffices.

## 5. Distinguishing `@Autowired` Config Methods from `@Bean` Factory Methods

Both method types accept multiple parameters, yet **serve different roles**.

### 5.1. `@Autowired` Instance Method

~~~java
public final class OrderEngine {
    @Autowired(required = false)
    public void configureExtras(AuditSink audit, MetricSink metrics) {
        // Store references for later use.
    }
}
~~~

This method belongs to an **already instantiated bean** and is invoked by Spring to configure the object. It **does not register a new bean** merely by carrying `@Autowired`; any return value (if declared) is not a bean product like `@Bean`.

### 5.2. `@Bean` Factory Method Taking Multiple Parameters

~~~java
@Configuration(proxyBeanMethods = false)
public class AppConfig {
    @Bean
    public OrderEngine orderEngine(Repository repository,
                                   Formatter formatter,
                                   @Value("${app.label:BASE}") String label) {
        return new OrderEngine(repository, formatter, label);
    }
}
~~~

This is an excerpt from the complete program in section 6. Spring:

1. Defines a bean definition via the `@Bean` method `orderEngine`.
2. Resolves `Repository` and `Formatter` using types and candidate-selection metadata.
3. Resolves the `${app.label:BASE}` placeholder into a configuration string defaulting to `BASE`.
4. Invokes the factory method with **all three resolved arguments**; the returned instance becomes the Spring-managed bean `orderEngine`.
5. Afterward, if the bean class has `@Autowired` methods, those configuration methods run at the appropriate lifecycle phase.

**You do not need to add `@Autowired` on a `@Bean` method** for Spring to pass parameters. `@Bean` already declares the bean creation point and factory-argument resolution.

### Comparison Table

| Property | `@Autowired` config method | `@Bean` factory method |
| --- | --- | --- |
| Where it lives | A container-managed bean | A `@Configuration` class or suitable config component |
| Purpose | Set dependencies on an existing object | Create or return an object to expose as a bean |
| Can take multiple parameters? | Yes | Yes |
| Must method be named `setX`? | No | No |
| Does return value create a bean? | No | **Yes**, the product of `@Bean` |
| How does `required=false` apply? | The whole method may be skipped if a dependency is missing | Normally factory params are requirements; express optionality via `Optional`/provider/suitable defaults |
| When does it run? | During the bean configuration phase | When the container needs to instantiate the bean per scope/lazy rules |
| Runs per business request? | No | No |

Do not put `@Autowired(required=false)` on a `@Bean` factory method merely to handle missing beans: factory method resolution should not be treated like an arbitrary configuration method. Use `Optional<T>` or conditional/factory configuration instead.

## 6. Runnable Spring Framework 6.2 / Java 17 Application

The example creates **two independent `ApplicationContext`s**. Both contain repository, formatter, and audit beans:

- **Context 1:** has no metrics bean. `OrderEngine.configureExtras(AuditSink, MetricSink)` is marked `@Autowired(required=false)`, so because metrics is missing, it **does not run**. By contrast, `OptionalObserver.configure(AuditSink, Optional<MetricSink>)` still runs and receives `Optional.empty()`.
- **Context 2:** additionally registers the metrics bean and puts `app.label=CUSTOM` into the environment before refresh. Both methods run; the use case prints audit and metric lines before printing the result.

### 6.1. Project Structure

Requires **JDK 17+**, Maven, and access to the Maven repository on the first dependency download. No Spring Boot, database, web server, or HTTP.

~~~text
multi-arg-injection/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── MultiArgumentDemo.java
~~~

Create `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>multi-arg-injection</artifactId>
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
                    <mainClass>demo.MultiArgumentDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.2. Complete Java File

Create `src/main/java/demo/MultiArgumentDemo.java`:

~~~java
package demo;

import java.util.Map;
import java.util.Objects;
import java.util.Optional;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.core.env.MapPropertySource;

public final class MultiArgumentDemo {
    private MultiArgumentDemo() {}

    public interface Repository {
        String find(String id);
    }

    public static final class DemoRepository implements Repository {
        @Override
        public String find(String id) {
            return "ROW(" + id + ")";
        }
    }

    public interface Formatter {
        String format(String text);
    }

    public static final class BracketFormatter implements Formatter {
        @Override
        public String format(String text) {
            return "[" + text + "]";
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

    public interface MetricSink {
        void record(String id);
    }

    public static final class ConsoleMetricSink implements MetricSink {
        @Override
        public void record(String id) {
            System.out.println("METRIC " + id);
        }
    }

    public static final class OrderEngine {
        private final Repository repository;
        private final Formatter formatter;
        private final String label;
        private AuditSink audit;
        private MetricSink metrics;
        private boolean extrasConfigured;

        public OrderEngine(Repository repository,
                           Formatter formatter,
                           String label) {
            this.repository = Objects.requireNonNull(repository);
            this.formatter = Objects.requireNonNull(formatter);
            this.label = Objects.requireNonNull(label);
        }

        // Arbitrary method name with 2 parameters.
        // If even one dependency is missing, the method is skipped.
        @Autowired(required = false)
        public void configureExtras(AuditSink audit, MetricSink metrics) {
            this.audit = Objects.requireNonNull(audit);
            this.metrics = Objects.requireNonNull(metrics);
            this.extrasConfigured = true;
        }

        public boolean extrasConfigured() {
            return extrasConfigured;
        }

        public String execute(String id) {
            String row = repository.find(id);
            if (extrasConfigured) {
                audit.record(id);
                metrics.record(id);
            }
            return label + ":" + formatter.format(row);
        }
    }

    public static final class OptionalObserver {
        private boolean methodCalled;
        private boolean metricsPresent;

        @Autowired
        public void configure(AuditSink audit,
                              Optional<MetricSink> metrics) {
            Objects.requireNonNull(audit);
            this.methodCalled = true;
            this.metricsPresent = metrics.isPresent();
        }

        public boolean methodCalled() {
            return methodCalled;
        }

        public boolean metricsPresent() {
            return metricsPresent;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class CoreConfig {
        @Bean
        public Repository repository() {
            return new DemoRepository();
        }

        @Bean
        public Formatter formatter() {
            return new BracketFormatter();
        }

        @Bean
        public AuditSink auditSink() {
            return new ConsoleAuditSink();
        }

        // Multi-argument factory method resolved automatically by Spring.
        @Bean
        public OrderEngine orderEngine(Repository repository,
                                       Formatter formatter,
                                       @Value("${app.label:BASE}") String label) {
            return new OrderEngine(repository, formatter, label);
        }

        @Bean
        public OptionalObserver optionalObserver() {
            return new OptionalObserver();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @Import(CoreConfig.class)
    public static class WithMetricsConfig {
        @Bean
        public MetricSink metricSink() {
            return new ConsoleMetricSink();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(CoreConfig.class)) {
            OrderEngine engine = context.getBean(OrderEngine.class);
            OptionalObserver observer =
                    context.getBean(OptionalObserver.class);

            System.out.println("-- no metrics --");
            System.out.println("ENGINE_METHOD " + engine.extrasConfigured());
            System.out.println("OBSERVER_METHOD " + observer.methodCalled());
            System.out.println("OBSERVER_METRICS " + observer.metricsPresent());
            System.out.println("RESULT " + engine.execute("A1"));
        }

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            // Property must be supplied before refresh.
            context.getEnvironment().getPropertySources().addFirst(
                    new MapPropertySource("demo",
                            Map.of("app.label", "CUSTOM")));

            context.register(WithMetricsConfig.class);
            context.refresh();

            OrderEngine engine = context.getBean(OrderEngine.class);
            OptionalObserver observer =
                    context.getBean(OptionalObserver.class);

            System.out.println("-- with metrics --");
            System.out.println("ENGINE_METHOD " + engine.extrasConfigured());
            System.out.println("OBSERVER_METHOD " + observer.methodCalled());
            System.out.println("OBSERVER_METRICS " + observer.metricsPresent());
            System.out.println("RESULT " + engine.execute("B2"));
        }
    }
}
~~~

### 6.3. Compiling and Running

From the `multi-arg-injection` directory containing `pom.xml`:

~~~bash
mvn -version
mvn -q compile exec:java
~~~

Maven may print dependency download progress or configuration-dependent logs. **Stdout lines intentionally printed by `MultiArgumentDemo` logic, in exact order:**

~~~text
-- no metrics --
ENGINE_METHOD false
OBSERVER_METHOD true
OBSERVER_METRICS false
RESULT BASE:[ROW(A1)]
-- with metrics --
ENGINE_METHOD true
OBSERVER_METHOD true
OBSERVER_METRICS true
AUDIT B2
METRIC B2
RESULT CUSTOM:[ROW(B2)]
~~~

`mvn -version` also prints Maven/JDK details. The block above describes **lines printed by the example code**, without claiming the entire terminal output consists solely of those lines.

### 6.4. Step-by-Step Analysis of Results

**Context 1 — without metrics:**

1. Spring reads `CoreConfig`, creates the three dependency beans `Repository`, `Formatter`, `AuditSink`, and the service beans per `@Bean`.
2. `orderEngine(Repository, Formatter, String)` receives the repository, formatter, and label from the placeholder. Without `app.label`, `@Value("${app.label:BASE}")` yields `BASE`.
3. Spring creates `OrderEngine`, then processes `@Autowired(required=false)` on `configureExtras(AuditSink, MetricSink)`.
4. Because **no `MetricSink` bean exists**, the entire method is skipped, and `extrasConfigured` remains `false`. The audit bean exists yet **is not attached alone** to the engine.
5. Spring creates `OptionalObserver`, then invokes `configure(AuditSink, Optional<MetricSink>)`; `AuditSink` exists while `MetricSink` does not, so Spring passes `Optional.empty()` and sets `methodCalled=true`, `metricsPresent=false`.
6. `execute("A1")` fetches `ROW(A1)`, applies the formatter to yield `[ROW(A1)]`, and returns `BASE:[ROW(A1)]` without printing audit or metric lines.

**Context 2 — with metrics:**

1. `MapPropertySource` supplies `app.label=CUSTOM` before `refresh()`, so the factory method receives `CUSTOM`.
2. `WithMetricsConfig` imports `CoreConfig` and adds the `MetricSink` bean.
3. This time both `AuditSink` and `MetricSink` exist, so Spring calls `configureExtras(...)`; `extrasConfigured=true`.
4. `OptionalObserver.configure(...)` runs, and `Optional<MetricSink>` contains a value, so `metricsPresent=true`.
5. `execute("B2")` invokes audit and metric **before returning the result string**. Both `AUDIT B2` and `METRIC B2` appear before `RESULT CUSTOM:[ROW(B2)]` printed by `main`.

The two contexts do not share default singleton instances; they run sequentially and are closed individually. There are no database transactions, HTTP servers, or Spring AOP in this example.

**Note:** The program prints nothing inside constructors or `@Bean` factory methods, so stdout does not depend on creation order across unrelated singletons.

## 7. Using `@Qualifier` and `@Primary` with Multiple Parameters

When two beans implement the same interface, type alone may not suffice to pick one:

~~~java
@Bean("fastFormatter")
Formatter fastFormatter() { return new FastFormatter(); }

@Bean("safeFormatter")
Formatter safeFormatter() { return new SafeFormatter(); }
~~~

This is an **illustrative, non-runnable** snippet missing the two classes. If a method expects one `Formatter` while multiple candidates exist with no selection rule, it can fail due to ambiguity.

Explicit selection directly on **each parameter**:

~~~java
@Autowired
public void configure(@Qualifier("safeFormatter") Formatter formatter,
                      AuditSink audit) {
    this.formatter = formatter;
    this.audit = audit;
}
~~~

This snippet requires importing `org.springframework.beans.factory.annotation.Qualifier` and the corresponding fields/interfaces.

- `@Qualifier("safeFormatter")` narrows candidates for the formatter parameter.
- `AuditSink` is still resolved independently by its own type/qualifiers.
- `@Primary` placed on a candidate bean can supply default priority for single-valued injection.
- When multiple primary beans match or a qualifier does not match, investigate the specific cause; never rely on bean declaration order.

**With multiple parameters, each parameter has its own selection metadata.** A qualifier annotation on the formatter parameter does not determine how the audit parameter is resolved.

One useful detail: JSR-250's `@Resource` is primarily designed for fields or JavaBeans setters with **a single parameter**; it is not a direct replacement for a multi-argument `@Autowired` method. Spring's parameter-level qualifiers in configuration methods fit this scenario better.

## 8. Method Injection with Collections and Multiple Implementations

Spring can inject groups of beans by type:

~~~java
@Autowired
public void configureAll(List<Formatter> formatters,
                         Map<String, AuditSink> audits) {
    this.formatters = formatters;
    this.audits = audits;
}
~~~

This is an **illustrative snippet**, requiring `java.util.List`, `java.util.Map`, and the actual fields/classes. When satisfied, `List<Formatter>` receives matching formatter beans; `Map<String, AuditSink>` uses bean names as keys and bean instances as values.

Points to keep in mind:

- List, array, Set, and Map have their own semantics; do not rely on Map iteration order unless an explicit ordering rule guarantees it.
- `@Order`/`Ordered` can influence ordering in matching injected collections, yet **it is not primary selection metadata for a single-value parameter**.
- With `@Autowired(required=true)` on a regular method, an empty collection may fail to satisfy the requirement if no matching beans exist; exceptions exist on certain constructor/factory-method resolution paths. Therefore, if a collection may be empty, design and verify against your actual Spring API and version.
- A multi-argument config method mixing collections and required scalars must still resolve every parameter at the same injection point.

**Do not manually declare a `@Bean List<Formatter>` merely to use multiple formatters** when the actual goal is “inject all beans implementing this interface”; Spring supports collection injection directly for that case.

## 9. When Spring Calls Config Methods and Lifecycle Timing

The `@Autowired` annotation is processed by Spring's bean post-processing:

~~~text
instantiate bean (constructor or factory)
    |
    +--> populate properties / @Autowired method injection
    |
    +--> aware callbacks, @PostConstruct / matching init callbacks
    |
    +--> bean ready for getBean / subsequent injection
~~~

General overview, not an exhaustive list of every extension point across all configurations.

Consequences:

1. **Method injection is a configuration step**: the method should set needed references/initial configuration, not execute customer use cases.
2. **Timing can be early**: non-lazy singletons are typically instantiated during `ApplicationContext.refresh()`, so config methods may run at startup.
3. **Scope matters**: each new prototype bean runs its own injection step on every request; singletons are typically configured once inside the container.
4. **Does not run automatically on manually instantiated objects**: `new OrderEngine(...)` outside a Spring container does not trigger `@Autowired` methods. Unit tests can invoke configuration methods directly if needed.
5. **Do not create unintended dependency cycles**: if A's config method requires B and B requires A, you can hit a dependency cycle and initialization failure; do not use setters merely to paper over design flaws.
6. **No automatic hot-reload**: changing a bean definition or PropertySource after a bean is configured does not mean Spring will automatically re-invoke all config methods to update the bean.

An ideal multi-argument method should be brief, deterministic, and free of uncontrolled I/O. If it is a singleton bean used across threads, avoid mutating configuration fields from other threads once running without proper concurrency design.

## 10. Why Is Constructor Injection Still Recommended for Required Dependencies?

If repository and formatter are prerequisites for handling requests, keep them in the constructor:

~~~java
public OrderEngine(Repository repository,
                   Formatter formatter,
                   String label) {
    this.repository = Objects.requireNonNull(repository);
    this.formatter = Objects.requireNonNull(formatter);
    this.label = Objects.requireNonNull(label);
}
~~~

Constructor fields can be `final`; the constructed object already meets the minimum requirements to operate. The audit/metrics extensions are grouped in `configureExtras` because the demo illustrates them as an **optional add-on configuration** that may be present or absent.

**It is not a rigid rule that constructors are good and all setters are bad.** What matters is:

- Required dependencies should appear clearly in the constructor.
- Optional dependencies can go through setters/config methods or `Optional<T>`.
- Dependencies that must be installed atomically can be grouped into a multi-argument method with clear semantics.
- A class with too many dependencies may be holding too many responsibilities; consider splitting responsibilities rather than just “moving everything to a config method”.

Methods marked `@Autowired` do not force domain tests to boot a Spring context: they remain ordinary Java methods that can be called directly when needed.

## 11. Common Misconceptions and Errors

| Misconception / Error | Correct Understanding |
| --- | --- |
| “`@Autowired` only works on constructors and setters.” | It can be placed on an arbitrary instance method taking multiple parameters. |
| “A method named `prepare` will be ignored because it doesn't start with `set`.” | Method name is not a restriction for `@Autowired`. |
| “Spring invokes a multi-argument method separately once per parameter.” | Spring resolves all arguments and then calls the method in a single Java invocation. |
| “`required=false` passes `null` for a missing dependency and still runs the method.” | If one dependency is missing, a non-required method may be skipped **entirely**. |
| “`Optional<MetricSink>` makes the whole method optional by default.” | Only that parameter is optional; other dependencies can still be required. |
| “`required=false` also resolves ambiguous multiple-bean errors.” | Qualifiers, `@Primary`, or explicit selection are still required. |
| “A multi-argument `@Bean` method needs `@Autowired` to receive parameters.” | Spring automatically resolves factory method arguments. |
| “An `@Autowired` config method registers an extra bean.” | It configures an existing bean; `@Bean` methods declare bean products. |
| “`@Value` automatically reads `application.properties` like Spring Boot.” | Plain Spring Framework needs explicit environment/property sources; the demo uses `MapPropertySource` explicitly. |
| “`@Autowired` runs on any object instantiated with `new`.” | Annotations are processed by the Spring container, not automatically by the JVM. |
| “If one bean is missing, Spring still half-runs the method.” | A method call is atomic; Spring never calls it with a partial parameter list. |
| “A 20-parameter config method is good design because there are fewer methods.” | It likely signals the class does too much and responsibilities should be split. |
| “A qualifier picking formatter also picks audit.” | Each parameter has independent resolution metadata. |
| “Singleton beans are automatically thread-safe.” | Injection and scope do not synchronize mutable state automatically. |
| “Putting `@Autowired` on a business method makes Spring call it before every request.” | No, it is a configuration injection point, not a request interceptor. |

### Common Diagnostic Exceptions

- `NoSuchBeanDefinitionException`: a required dependency type has no bean in the context.
- `NoUniqueBeanDefinitionException`: multiple candidates exist for one parameter with no unambiguous choice.
- `UnsatisfiedDependencyException`: an injection point could not be satisfied.
- `BeanCreationException`: failure instantiating/configuring/initializing a bean, usually wrapping an inner cause.
- `BeanCurrentlyInCreationException`: an unresolved dependency cycle.
- `IllegalArgumentException` from a config method: e.g., a setter validating an argument or invalid business invariant.

Read the **bean name and injection point** in the stack trace before editing configuration. Do not mark an entire method `required=false` just to mask a genuinely required dependency.

## 12. Practice Exercises with Answers

**Exercise 1.** Method `@Autowired(required=false) void configure(AuditSink a, MetricSink m)` has an audit bean present but no metrics bean. Will Spring call the method with `m=null`, or skip it?

**Answer:** It skips the method when a dependency is missing; initial fields keep their default state. That is non-required method semantics, not partial injection.

**Exercise 2.** What happens for `@Autowired void configure(AuditSink a, Optional<MetricSink> m)` when audit exists and metrics is missing?

**Answer:** The method is called with the audit bean and `Optional.empty()` for metrics, assuming no other errors. This is optionality **on an individual parameter**.

**Exercise 3.** A method in `@Configuration` is `@Bean Foo foo(Bar bar, Baz baz)`. Must `@Autowired` be placed on it to receive both dependencies?

**Answer:** No. The container recognizes the factory method as a bean creation point via `@Bean` and resolves its parameters automatically.

**Exercise 4.** Why does the demo's first context print `ENGINE_METHOD false` yet `OBSERVER_METHOD true`?

**Answer:** The engine's `required=false` config method lacks `MetricSink` so it is skipped; the observer's method uses an `Optional<MetricSink>` parameter so it is still called with `Optional.empty()`.

**Exercise 5.** Why do `AUDIT B2` and `METRIC B2` appear before `RESULT CUSTOM:[ROW(B2)]`?

**Answer:** `OrderEngine.execute` calls both collaborators before returning the string. `main` only prints the result after the method returns.

**Exercise 6.** If the `Formatter` interface has two implementations and both are registered as beans, how do you resolve it?

**Answer:** Supply an intentional selection rule, such as a qualifier directly on the parameter or an appropriate `@Primary` bean. Do not rely on method declaration order in the source file.

**Exercise 7.** If a config method takes `List<AuditSink>`, is that the same as a single `AuditSink` parameter?

**Answer:** No. Collection injection can receive multiple matching beans, whereas a single parameter must resolve to exactly one candidate.

**Exercise 8.** If you call `new OrderEngine(repo, fmt, label)` outside Spring, does `@Autowired(required=false) configureExtras(...)` run automatically?

**Answer:** No. Annotations inside the class are not enough on their own. If manual configuration is needed, call the method directly or use an appropriate factory.

**Exercise 9.** To make audit and metric optional **independently** of each other, how should you design it?

**Answer:** Split into two separate non-required injection methods, or express independent optionality with `Optional<T>`/providers depending on the case.

## 13. Project Checklist

- [ ] Distinguish `@Autowired` configuration methods from `@Bean` factory methods.
- [ ] Ensure the bean to be configured is registered in the Spring context.
- [ ] Methods annotated with `@Autowired` are instance methods with clear signatures; names do not need `set...`.
- [ ] Verify all parameter types have matching candidates.
- [ ] When multiple candidates exist, select using `@Qualifier`/`@Primary` on the right parameter.
- [ ] Use `required=true` (default) for genuinely required configuration.
- [ ] Use `required=false` when **the entire group of dependencies** can be absent while keeping the object valid.
- [ ] Do not expect a non-required method to receive `null` for missing arguments.
- [ ] If individual parameters are independently optional, use `Optional<T>` or separate injection points.
- [ ] Put required dependencies in the constructor where appropriate to avoid partially ready objects.
- [ ] For multi-parameter `@Bean` methods, let the container resolve parameters instead of calling `getBean` manually.
- [ ] When using `@Value` properties, validate defaults and register property sources before refresh.
- [ ] Do not hide business use cases in lifecycle methods or print unpredictable output at startup.
- [ ] Test contexts both with and without optional dependencies; verify stdout and actual bean state.
- [ ] Never hot-swap singleton fields without a thread-safety strategy.
- [ ] Close the context after the application finishes.

### Official Spring Documentation

- [Using @Autowired](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
- [Fine-tuning Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)

**Conclusion:** In Spring Core Container, a **multi-argument `@Autowired` configuration method** lets you wire multiple collaborators onto a bean in one method invocation. With `required=false`, the method is generally **skipped completely** if a dependency is missing; with `Optional<T>`, optionality is expressed on a specific parameter. Conversely, a **multi-argument `@Bean` factory method** creates a bean and receives resolved arguments from Spring automatically. Clearly understanding these three mechanisms helps you define required dependencies, optional dependencies, and atomic configuration groups accurately instead of confusing bean creation with configuration injection.