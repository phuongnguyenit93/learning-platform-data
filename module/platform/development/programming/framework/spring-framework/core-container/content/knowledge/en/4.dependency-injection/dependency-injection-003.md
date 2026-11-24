# Setter Injection for Optional Configuration in Spring Core Container

## 1. Goal: Required Dependencies vs. Optional Configuration

**Setter injection** is how Spring supplies a value or collaborator to a bean through a **setter method** after the object has been created. This technique is particularly useful when a dependency is **not a mandatory condition** for the object to perform its primary task, or when a parameter has a **sensible default value** that can still be overridden via configuration.

For example, `ReportService` always needs `ReportRepository` to retrieve report data, yet it may:

- Have or omit an `AuditSink` to record processing traces.
- Use the default display prefix `REPORT`, or override it with a configured value such as `CUSTOM`.

The appropriate design is:

- **Constructor injection** for `ReportRepository`: without the repository, the service cannot function.
- **Setter injection** for `AuditSink`: if auditing is absent, the core function still runs.
- **Property-accepting setter** for the report prefix: has a valid default; configuration only overrides it when needed.

~~~text
ApplicationContext
     |
     +-- create ReportRepository bean
     |
     +-- call new ReportService(repository)  [required]
     |         |
     |         +-- @Value setter: prefix = REPORT or CUSTOM
     |         |
     |         +-- @Autowired(required=false) setter:
     |                    AuditSink bean present -> call setter
     |                    AuditSink bean missing -> skip setter
     |
     +-- return configured ReportService bean
                      |
                      +-- render(id) -> repository.find(id)
                                      -> audit if present
                                      -> result string
~~~

**Core point:** “optional” does not mean Spring will always pass `null`. With `@Autowired(required = false)` placed on a method, if the dependency is unavailable, Spring may **skip calling that method**. Thus the default state already initialized in the object is preserved.

## 2. How Do Constructor Injection and Setter Injection Differ?

| Criterion | Constructor injection | Setter injection |
| --- | --- | --- |
| When dependency is supplied | At object creation | After object creation, during bean configuration |
| Best suited for | Required dependencies, invariants for object validity | Dependencies/config options with clear defaults |
| Can use `final` fields? | Usually yes, assigned in constructor | Cannot reassign `final` via a normal setter |
| If dependency is missing | Typically fails at bean creation | Depends on config: fail, skip, or keep default |
| Flexibility after creation | Less likely to swap references | Can reconfigure, though lifecycle/thread safety must be controlled |
| Plain Java unit tests | Pass dependencies to constructor | Create object then explicitly call setters |
| Risk | Too many constructor params may signal the class holds too many responsibilities | Bean can end up in a partially configured state if misused |

Plain Java example:

~~~java
public final class ReportService {
    private final ReportRepository repository;  // required
    private String prefix = "REPORT";            // default value

    public ReportService(ReportRepository repository) {
        this.repository = java.util.Objects.requireNonNull(repository);
    }

    public void setPrefix(String prefix) {        // optional
        this.prefix = prefix;
    }
}
~~~

This is an **illustrative snippet**, lacking `ReportRepository` and processing logic, so it is not a standalone runnable file. The block above shows that Java already supports setter injection in the sense of “external code calls a setter to configure”; **Spring did not invent setters**, it invokes them using metadata and dependency resolution.

**Design rule:** do not move every constructor parameter to setters merely to shrink the parameter list. A class that is considered “successfully constructed” without its critical dependencies can throw a `NullPointerException` much later during business execution. For required dependencies, constructor injection is generally more transparent and safer.

## 3. A Setter Is a Configuration Point, Not Exclusive to Spring

A traditional setter has the signature:

~~~java
public void setAuditSink(AuditSink sink) {
    this.auditSink = sink;
}
~~~

If startup code does it directly:

~~~java
ReportService service = new ReportService(repository);
service.setAuditSink(new ConsoleAuditSink());
~~~

then that is **manual setter injection**. The types in both blocks are assumed to be already defined; the complete program is in section 6.

Spring configuration can invoke setters in three common ways:

1. **Explicit setter call in a `@Bean` factory method**: when creating the bean, Java config explicitly calls `set...`.
2. **`@Autowired` annotation on a setter**: Spring attempts to locate a matching bean and invokes the setter via `AutowiredAnnotationBeanPostProcessor`.
3. **Property injection from XML**: `<property name="auditSink" ref="auditSink"/>` instructs Spring to apply the JavaBeans property setter.

For scalar values from the environment, a method accepting `@Value("${app.report.prefix:REPORT}")` can receive the property string resolved by Spring and store it in a field. The `${key:default}` syntax uses what follows `:` as the default value if no matching key exists.

Do not treat all these mechanisms as identical. Calling a setter directly in `@Bean` is decided by **configuration code**; `@Autowired` has bean candidate and `required` semantics; `@Value` relies on property resolution, whereas XML `<property>` is bean definition metadata.

## 4. `@Autowired(required = false)`: The Setter Can Be Skipped

### 4.1. Syntax and Semantics

~~~java
private AuditSink auditSink;  // defaults to null: no audit

@Autowired(required = false)
public void setAuditSink(AuditSink auditSink) {
    this.auditSink = auditSink;
}
~~~

This is an excerpt from the runnable program in section 6. In an `ApplicationContext` with annotation processing enabled:

- If a matching `AuditSink` bean exists, Spring invokes the setter and stores the reference.
- If **no** matching bean exists, **the setter is not invoked**, and the field retains its declared default value.
- For a method with **multiple parameters**, `required = false` applies to the whole method: if even one dependency is unavailable, the entire method may be skipped.
- If **multiple `AuditSink` beans match without a single winner**, `required = false` is not an ambiguity-resolution mechanism: `@Qualifier`, `@Primary`, or proper configuration is still needed.
- If a bean exists but creating that dependency fails, do not assume `required = false` swallows constructor/factory exceptions or misconfigurations.
- If the setter is invoked and **the setter body itself throws an exception**, bean creation can still fail.

In other words, `required = false` means **the injection point does not have to be satisfied**, not “ignore errors of any kind”.

### 4.2. Designing Behavior When the Dependency Is Absent

If auditing is genuinely optional, calling code must handle its absence explicitly:

~~~java
if (auditSink != null) {
    auditSink.record(reportId);
}
~~~

Another approach is the **Null Object pattern**: initialize the reference with a no-op implementation, then let the setter override it when a real bean exists:

~~~java
private AuditSink auditSink = reportId -> { };

@Autowired(required = false)
public void setAuditSink(AuditSink auditSink) {
    this.auditSink = java.util.Objects.requireNonNull(auditSink);
}
~~~

If no bean exists, the setter is skipped and the default audit implementation stays silent. This avoids `null` checks at every call site, though naming and semantics must be clear so missing audit is not accidentally masked when auditing is a mandatory requirement.

In the runnable program in section 6, we use `null` + an explicit check so `AUDIT_ENABLED false/true` is easy to observe.

### 4.3. `Optional<T>` and `ObjectProvider<T>` as Alternatives

When a dependency only expresses “present or absent”, you can also write:

~~~java
public ReportService(ReportRepository repository,
                     java.util.Optional<AuditSink> optionalAudit) {
    this.repository = repository;
    this.auditSink = optionalAudit.orElse(null);
}
~~~

This is an **illustrative constructor snippet** needing the corresponding fields and interfaces. Spring supports injecting `Optional<T>`; this lets optional dependencies be declared directly in the constructor without forcing a setter.

If a collaborator must be fetched **on demand at runtime**, consider `ObjectProvider<AuditSink>`, such as `getIfAvailable()`. However:

- Do not use a provider merely to replace a simple optional reference.
- Read the contract of `getIfAvailable()`, including what happens when multiple candidates cause ambiguity.
- Do not conflate configuration optionality with picking a different implementation per request.

For scalar configuration properties, `@Value` with a default or a Spring Boot `@ConfigurationProperties` bean (when using Boot) is typically more fitting than an `Optional<Bean>` just to hold a string.

## 5. `@Value` on a Setter: Defaults and External Configuration

### 5.1. Default Values via Placeholders

~~~java
private String prefix = "REPORT";

@Value("${app.report.prefix:REPORT}")
public void setPrefix(String prefix) {
    this.prefix = prefix;
}
~~~

When the `app.report.prefix` property does not exist, Spring uses the default `REPORT`. If the property has value `CUSTOM`, the setter receives `CUSTOM`.

Distinguish:

- **Java default field:** `private String prefix = "REPORT";` is present as soon as the constructor finishes.
- **Property placeholder default:** `${app.report.prefix:REPORT}` is Spring's resolution rule when the key is not supplied.
- **Setter body validation:** if needed, the method should check that prefix is non-null/non-blank to avoid accepting meaningless configuration.
- **`@Value` does not mean `@Autowired(required=false)`:** `@Value` supplies a resolved value; optional bean injection has its own semantics.
- **An empty or whitespace-only property** may still resolve to an empty/blank string rather than triggering the default value. Therefore, validate if configuration data must be non-empty.

In the demo, Spring supplies a `MapPropertySource` for the second context, creating an explicit configuration key without needing an `application.properties` file or Spring Boot dependencies.

### 5.2. Using a Factory Method Instead of `@Value`

Another approach is injecting `Environment` into a `@Bean` method and **calling the setter purposefully**:

~~~java
@Bean
ReportService reportService(ReportRepository repository,
                            Environment env) {
    ReportService service = new ReportService(repository);
    service.setPrefix(env.getProperty("app.report.prefix", "REPORT"));
    return service;
}
~~~

This is an **illustrative alternative snippet**, not an extra factory method in the main program. In a real project, import `org.springframework.core.env.Environment` and the relevant classes.

This keeps configuration wiring in one place, making defaults and validation easy to control. It also lets the business class **avoid importing Spring annotations**. In exchange, the configuration class must know the setter and supply the value.

When a class has many properties, avoid dozens of scattered setters if they can be grouped into an **immutable configuration object** that is validated and injected via constructor.

## 6. Complete Runnable Java 17 / Spring Framework 6.2 Program

The example intentionally creates two independent contexts:

- **Default context:** has `ReportRepository` and `ReportService`, but **no `AuditSink`** and no `app.report.prefix` property. The service still runs; the audit setter is not called; the default prefix is `REPORT`.
- **Customized context:** additionally registers `AuditSink` and sets `app.report.prefix=CUSTOM` **before `refresh()`**. Spring invokes the audit setter; the prefix setter receives `CUSTOM`.

No HTTP, database, or network I/O. Auditing only prints a line to the console. The example uses `spring-context`, JDK 17, and Maven; no Spring Boot required.

### 6.1. Structure and Maven

~~~text
optional-setter-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── OptionalSetterDemo.java
~~~

Contents of `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>optional-setter-demo</artifactId>
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
                    <mainClass>demo.OptionalSetterDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.2. Complete Java File

Save `src/main/java/demo/OptionalSetterDemo.java`:

~~~java
package demo;

import java.util.Map;
import java.util.Objects;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.core.env.MapPropertySource;

public final class OptionalSetterDemo {
    private OptionalSetterDemo() {}

    public interface ReportRepository {
        String find(String id);
    }

    public static final class DemoRepository implements ReportRepository {
        @Override
        public String find(String id) {
            return "ITEM(" + id + ")";
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

    public static final class ReportService {
        private final ReportRepository repository;
        private AuditSink auditSink;       // optional, absent by default
        private String prefix = "REPORT";  // default is always valid

        public ReportService(ReportRepository repository) {
            this.repository = Objects.requireNonNull(
                    repository, "repository");
        }

        @Autowired(required = false)
        public void setAuditSink(AuditSink auditSink) {
            this.auditSink = Objects.requireNonNull(
                    auditSink, "auditSink");
        }

        @Value("${app.report.prefix:REPORT}")
        public void setPrefix(String prefix) {
            if (prefix == null || prefix.isBlank()) {
                throw new IllegalArgumentException(
                        "report prefix must not be blank");
            }
            this.prefix = prefix;
        }

        public String render(String id) {
            String value = repository.find(id);
            if (auditSink != null) {
                auditSink.record(id);
            }
            return prefix + ":" + value;
        }

        public boolean hasAuditSink() {
            return auditSink != null;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class BaseConfig {
        @Bean
        public ReportRepository reportRepository() {
            return new DemoRepository();
        }

        @Bean
        public ReportService reportService(ReportRepository repository) {
            return new ReportService(repository);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @Import(BaseConfig.class)
    public static class WithAuditConfig {
        @Bean
        public AuditSink auditSink() {
            return new ConsoleAuditSink();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(BaseConfig.class)) {
            ReportService service = context.getBean(ReportService.class);
            System.out.println("-- default --");
            System.out.println("TEXT " + service.render("A1"));
            System.out.println("AUDIT_ENABLED " + service.hasAuditSink());
        }

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {
            context.getEnvironment().getPropertySources().addFirst(
                    new MapPropertySource("demo",
                            Map.of("app.report.prefix", "CUSTOM")));

            context.register(WithAuditConfig.class);
            context.refresh();

            ReportService service = context.getBean(ReportService.class);
            System.out.println("-- customized --");
            System.out.println("TEXT " + service.render("B2"));
            System.out.println("AUDIT_ENABLED " + service.hasAuditSink());
        }
    }
}
~~~

`@Autowired(required = false)` sits **on the setter method**, not the constructor. `@Value` is processed on another setter. Both `ReportService` beans are created by `@Bean` factory methods, so Spring still applies bean post-processors to process annotations on the managed bean.

### 6.3. Commands and stdout

From the `optional-setter-demo` directory:

~~~bash
mvn -version
mvn -q compile exec:java
~~~

If this is the first time running Maven, dependencies may need to be downloaded from the repository. **Lines printed by the program to stdout in exact order:**

~~~text
-- default --
TEXT REPORT:ITEM(A1)
AUDIT_ENABLED false
-- customized --
AUDIT B2
TEXT CUSTOM:ITEM(B2)
AUDIT_ENABLED true
~~~

`mvn -version` as well as Maven/plugins may print their own version details and logs. The stdout block describes **lines printed by `OptionalSetterDemo` logic**, without claiming the terminal will always contain only these seven lines.

### 6.4. Tracing the Real Mechanism

1. `AnnotationConfigApplicationContext(BaseConfig.class)` creates and refreshes the first context. Spring instantiates `DemoRepository` and `ReportService`.
2. The `ReportService(ReportRepository)` constructor receives the required repository without looking up beans itself.
3. No `AuditSink` bean exists in the first context, so the `@Autowired(required=false)` injection method **is skipped**, and `auditSink` remains `null`.
4. No `app.report.prefix` key exists, so `@Value("${app.report.prefix:REPORT}")` uses the default `REPORT`; the prefix setter is invoked.
5. `render("A1")` fetches `ITEM(A1)` from the repository, skips auditing, and returns `REPORT:ITEM(A1)`.
6. The second context adds `MapPropertySource` with value `CUSTOM` **before** registering/refreshing. `@Import(BaseConfig.class)` brings the repository and service definitions into the same context as the `AuditSink` bean.
7. Spring finds a matching `AuditSink` bean, so it calls `setAuditSink(ConsoleAuditSink)` while configuring `ReportService`. The prefix setter receives `CUSTOM`.
8. `render("B2")` calls `auditSink.record("B2")`, printing `AUDIT B2` **before** `main` prints `TEXT CUSTOM:ITEM(B2)`. Finally, `hasAuditSink()` returns `true`.
9. The two contexts are independent: one context's `ReportService` singleton is not shared by default with the other. `try-with-resources` closes each context.

**Key takeaway:** in both runs, the `render` logic did not need to change. The optional component and prefix were determined by how Spring assembled and configured the bean.

## 7. XML Property Injection: Another Way to Configure Setters

An XML configuration can supply values to JavaBeans setters:

~~~xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="http://www.springframework.org/schema/beans
                           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="repository" class="demo.DemoRepository"/>

    <bean id="reportService" class="demo.ReportService">
        <constructor-arg ref="repository"/>
        <property name="prefix" value="REPORT"/>
    </bean>
</beans>
~~~

This is **illustrative XML**, not an XML file intended to run directly against the Java example with nested classes in section 6. In real usage, replace `demo.DemoRepository` and `demo.ReportService` with actual top-level class names in the project, or extract the classes into separate files as in standard design.

`<property name="prefix">` maps to the JavaBeans method `setPrefix(String)`. If you add:

~~~xml
<property name="auditSink" ref="auditSink"/>
~~~

then a corresponding `auditSink` bean must be registered for Spring to pass via the setter. If an XML property references a nonexistent bean, that is **not automatically optional injection**: the context may fail when creating the bean. Thus, explicit `<property ref>` syntax differs from `@Autowired(required=false)`.

In legacy XML, `autowire="byName"` or `autowire="byType"` also exist to automatically wire matching properties. These modes have their own rules and can introduce ambiguity, so they should not be chosen merely to avoid writing explicit configuration for important dependencies.

## 8. Why Shouldn't You Use Setters for Every Dependency?

### 8.1. Incomplete State

If a business object requires a repository yet only declares:

~~~java
class BadReportService {
    private ReportRepository repository;

    public void setRepository(ReportRepository repository) {
        this.repository = repository;
    }

    public String render(String id) {
        return repository.find(id);
    }
}
~~~

This is an illustrative snippet assuming `ReportRepository` already exists. `new BadReportService().render("A1")` throws a `NullPointerException` because the repository has not been set yet. Using a constructor with `Objects.requireNonNull` detects the missing dependency **right when creating the service**, rather than deferring it until business execution.

An “optional” setter must genuinely have valid behavior when not called; otherwise, it is actually a required dependency placed in the wrong spot.

### 8.2. Runtime Mutation and Concurrency

A singleton bean is shared across callers. Even with a public setter, **do not arbitrarily invoke the setter after the bean is already serving requests** if doing so mutates state unsynchronized. For instance, one thread running `render` while another calls `setPrefix` can observe inconsistent configuration; a setter does not automatically create synchronization or transactions.

In typical applications, setter injection is **an initial container configuration step**, not an invitation to mutate runtime configuration unchecked. If hot reloading is required, use safe, explicit state management or immutable snapshots.

### 8.3. Do Not Work Around Dependency Cycles at Any Cost

Setter injection can in some cases allow the container to resolve certain dependency cycles that constructor injection cannot, yet **a dependency cycle is usually a design smell worth reviewing**. Do not convert constructors into setters merely to hide an A↔B graph; split responsibilities, introduce a mediator/events, or redesign ownership where appropriate.

Spring also has specific rules around proxies, singleton-in-creation caches, circular references, and Boot defaults. Do not extrapolate from an old example that modern Spring always resolves every setter injection cycle.

## 9. Handling Trickier Optional Scenarios

| Scenario | Suitable Choice | Notes |
| --- | --- | --- |
| Non-mandatory dependency, used if present | `@Autowired(required=false)` setter | Method is skipped when dependency is unsatisfied |
| Want optionality expressed explicitly in constructor | `Optional<T>` | No need to convert every dependency to a setter |
| Need lazy or on-demand dependency lookup | `ObjectProvider<T>` | Check semantics when missing or multiple beans exist |
| Config parameter with a default | `@Value("${key:default}")` or `Environment.getProperty(key, default)` | Validate empty/invalid values |
| Configuration with many related fields | Validated config bean, constructor injection | Reduces scattered mutable setters |
| Multiple beans implementing the same interface | `@Qualifier` or `@Primary` | `required=false` does not resolve ambiguity |
| Need default behavior when collaborator is absent | Null Object or explicit branch | Do not silently mask missing required dependencies |
| Choose implementation per request | Strategy/router based on business data | Do not use bean injection to replace runtime decisions |
| Change configuration while serving multiple threads | Explicit snapshot/thread-safe design | Plain setters do not solve concurrency |

### Multi-Argument Optional Method

~~~java
@Autowired(required = false)
public void configure(AuditSink audit, MetricsSink metrics) {
    this.audit = audit;
    this.metrics = metrics;
}
~~~

This is an **illustration**; `MetricsSink` and the fields are not defined here. If either dependency is missing, a non-required method may **be skipped completely**. If the two dependencies are **independently optional**, split them into two injection points or use `Optional<T>`/providers appropriately, rather than bundling them into one setter and accidentally coupling their presence.

### Interaction with `@Bean` and Annotation Processing

`@Autowired`/`@Value` are applied by a `BeanPostProcessor`. `AnnotationConfigApplicationContext` registers the necessary annotation processors in standard setups, including processing beans returned from `@Bean` methods.

However, if you **manually call `new ReportService(repo)` outside a Spring context**, setter annotations **do not run automatically**. You must call the setters yourself or hand the object over to explicit bean management/configuration. `@Autowired` is not syntax executed automatically by the JVM upon constructor invocation.

In beans that are themselves a `BeanFactoryPostProcessor` or `BeanPostProcessor`, do not assume injection annotations apply the same way as on ordinary business beans: post-processing components are instantiated at a special phase and have restrictions requiring explicit configuration.

## 10. Common Errors and Diagnosis

| Symptom | Cause / How to Handle |
| --- | --- |
| `@Autowired` setter never runs | Missing matching bean; `required=false` caused Spring to skip the method |
| Setter ran yet code still sees null | Verify the field is actually assigned, check null guards and bean lifecycle |
| Bean is missing yet context still starts | This may be intended behavior if the dependency is genuinely optional |
| Required dependency is missing yet service still gets created | Poor boundary design; move the dependency to the constructor |
| Two optional beans of the same type cause startup failure | Disambiguate with qualifier/primary; optional does not mean picking arbitrarily |
| `@Value` does not pick up the expected default | Key may exist with an empty value; check property sources and validation |
| Property added after context was already refreshed | Add/configure property sources before bean creation to affect setters |
| `@Value` setter does not run on object created with `new` | Annotations are processed by Spring for managed beans, not directly by Java |
| XML `<property ref>` references missing bean | Explicit ref requires a valid bean name; not equivalent to an optional setter |
| `@Autowired(required=false)` on multi-arg method skips everything | One unresolvable parameter can cause the entire method to be skipped |
| Singleton bean changes config mid-runtime causing races | Requires dedicated concurrency/hot-reload design |
| Adding setter injection to patch every dependency cycle | Re-evaluate dependency graph architecture |
| Expecting Spring to create HTTP/transactions from setter annotations | DI does not add a web server or transaction manager by itself |

**Debugging workflow:** verify the class is actually a Spring-managed bean → annotation processors are registered → setter signature matches → candidate bean or property key exists → check for multiple candidates → inspect defaults when injection is skipped → trace root cause in the stack trace.

## 11. Practice Exercises with Answers

**Exercise 1.** `ReportRepository` is required, and `AuditSink` is only for tracing. How should they be injected?

**Answer:** Repository via constructor injection; audit can use an `@Autowired(required=false)` setter with safe behavior when absent. If auditing is actually compliance-mandated, do not mark it optional.

**Exercise 2.** Why can a context without `AuditSink` still render reports?

**Answer:** Spring skips the `@Autowired(required=false)` setter, leaving `auditSink` as `null`; `render` checks before invoking audit. The constructor still receives the full repository.

**Exercise 3.** Why does the second context print `AUDIT B2` before `TEXT CUSTOM:ITEM(B2)`?

**Answer:** `render` invokes `auditSink.record` while computing the result, then returns the string to `main` to print. Neither line is automatic Spring logging.

**Exercise 4.** If two `AuditSink` beans of the same type exist, does `required=false` automatically pick one?

**Answer:** No. Explicit selection rules via `@Primary`/`@Qualifier` or deliberate multi-bean injection design are needed.

**Exercise 5.** Is `@Value("${app.report.prefix:REPORT}")` equivalent to “read property or use REPORT if the value is whitespace”?

**Answer:** No. The default primarily applies when the property is not found; a provided blank value may need to be rejected or normalized manually. The demo's setter throws an error if blank.

**Exercise 6.** If an optional method declares two parameters and only one matching bean exists, will the method receive null for the other parameter?

**Answer:** Do not assume that. With an `@Autowired(required=false)` method, if one parameter has no dependency, the entire method may be skipped. Use `Optional<T>` per parameter to express independent optionality.

**Exercise 7.** Can `ReportService` be unit-tested without a Spring context?

**Answer:** Yes. Construct a fake `ReportRepository`, call the constructor; if needed, call `setAuditSink` and `setPrefix` manually, then assert `render` and calls on the fake. Annotations are not required for Java setter methods to run.

**Exercise 8.** Why shouldn't `ReportRepository` be replaced with an optional setter to be “more flexible”?

**Answer:** Because the service cannot render without a repository. A constructor turns a required dependency into a condition for creating a valid object, catching errors much earlier.

## 12. Practical Application Checklist

- [ ] Classify every dependency clearly: **required** vs. **optional**.
- [ ] Inject required dependencies via constructor, never leaving the service missing prerequisites to operate.
- [ ] Give optional setters safe defaults or explicit absence-handling branches.
- [ ] Place `@Autowired(required=false)` properly on setters and understand the method may be skipped.
- [ ] For multi-parameter methods, verify that `required=false` semantics apply to the whole method.
- [ ] Do not use `required=false` to resolve multiple beans of the same type or bean creation errors.
- [ ] Ensure `@Value` placeholders use valid default syntax and validate values when needed.
- [ ] Register property sources before `refresh()` or before beans need to be initialized.
- [ ] Understand the difference between calling setters inside `@Bean`, annotation autowiring, and XML properties.
- [ ] Avoid mixing multiple configuration sources (XML, annotations, manual) for one setter if precedence is unclear.
- [ ] Unit test the service with and without optional collaborators; integration test both profiles/configurations.
- [ ] When a singleton service runs across multiple threads, avoid arbitrarily mutating settings at runtime.
- [ ] Do not make every dependency optional just to keep the context from failing.
- [ ] Verify program stdout and distinguish it from Maven logs.
- [ ] Close `ApplicationContext` per its lifecycle and do not expect injection on objects created outside the container.

**Conclusion:** Setter injection is valuable when configuration or collaborators are **genuinely optional** and the object still behaves properly when the setter is never invoked. `@Autowired(required=false)` expresses skippable injection, `@Value` applies properties with defaults, while constructor injection keeps required dependencies explicit. That separation keeps beans valid from creation while staying flexible at appropriate configuration points.

### Further Reading in Spring Documentation

- [Setter-based Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Using @Autowired and required=false](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [Using @Value](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html)
- [Annotation-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config.html)