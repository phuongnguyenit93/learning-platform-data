# Distinguishing Selection Priority from Initialization Order — Spring Framework Core Container

## 1. Three Different Questions That Frequently Get Mixed Up

In Spring IoC Container, when multiple beans implement the same interface, a developer may need to **pick one bean**, **order multiple beans**, or **ensure one bean initializes before another**. These three requirements happen at different stages and cannot be solved with a single annotation.

Suppose an application has two beans of type `Sender`: `emailSender` and `smsSender`. Distinguish:

1. **Candidate selection priority:** If a constructor requires **one** `Sender`, which bean gets injected? This is candidate resolution. Common tools are `@Primary`, `@Qualifier`, `@Fallback`, or other bean selection rules.
2. **Order of collected candidates:** If a constructor requires `List<Sender>`, which element comes first in the list? This is collection ordering. Common tools are `@Order`, `Ordered`, or `jakarta.annotation.Priority` where appropriate.
3. **Initialization/lifecycle order:** Which bean does Spring **create and finish initializing** before another? This is governed by the dependency graph, `@DependsOn`, constructor dependencies, `@Lazy`, scope, and bootstrap schedule. `@Primary` and `@Order` are not directives controlling singleton startup order.

An important rule to remember:

> **Being preferred for selection does not mean being created first. Being first in a collection does not mean being created first either.**

This lesson places these three concepts side by side in **Spring Framework Core Container**, without Spring Boot so unrelated lifecycles or schedulers are avoided.

### Learning Objectives

After this lesson, you will be able to:

- Explain how single-bean injection differs from `List<Bean>` injection and from bean creation order.
- Know that `@Primary` chooses a default candidate, `@Qualifier` selects by consumer intent, and `@Fallback` lowers precedence in Spring 6.2.
- Know that `@Order` affects **element order in collections** and certain framework priority points, yet **does not control singleton startup order**.
- Use `@DependsOn` when initialization order is genuinely needed for side effects, and distinguish it from **passing dependencies via constructor**.
- Understand singleton eager initialization, `@Lazy`, prototype scope, circular dependencies, and the limits of relying on declaration order.
- Run a Java 17+ example with Spring Framework 6.2.19: a bean marked **`@Primary` and `@Order(1)` is initialized after** the other bean due to `@DependsOn`.
- Write smoke tests verifying the **right bean**, **right collection order**, and **right initialization relationship**, avoiding assumptions from incidental logs.
- Distinguish initialization order, destruction order, and business method invocation order.

**Scope:** candidate selection versus bean initialization order in the IoC container. The lesson requires no Spring Boot, MVC, transaction manager, thread scheduler, or dependencies outside Spring Context.

## 2. Distinction Table Before Writing Annotations

| Question | What to observe | Appropriate Spring tool | What not to infer |
| --- | --- | --- | --- |
| Pick **one** `Sender` | Constructor parameter `Sender` | `@Primary`, `@Qualifier`, `@Fallback`, candidate rules | Picked first means created first |
| Pick `Sender` for a specific domain role | `@Qualifier("emailSender") Sender` | Qualifier metadata and type resolution | Qualifier dictates init order |
| Gather and sort **multiple** `Sender`s | `List<Sender>` / array | `@Order`, `Ordered`, ordering comparator | `@Order(1)` automatically becomes primary |
| Force bean B to be created only after bean A | Bean definitions and dependency graph | Constructor/factory parameter, `@DependsOn("beanA")` | `@Primary` or `@Order` solves this relationship |
| Defer creating a singleton | Bean definition | `@Lazy` | Lazy means the dependency is always optional |
| Create a fresh object on every request | Bean scope | `@Scope("prototype")` | Prototypes are eagerly pre-instantiated like singletons |
| Control **shutdown** order via depends-on | Singleton lifecycle | `@DependsOn` + destruction callbacks | All beans share the same destruction order |
| Control business execution order | Application logic | Orchestrator / explicit method calls | Spring automatically invokes methods by bean `@Order` |

If a team says “priority” without specifying **priority for what action**, ask: “Single-dependency selection priority, list ordering priority, or startup priority?” Many bugs stem from calling all three “bean order”.

## 3. Choosing One Candidate with `@Primary`, `@Qualifier`, `@Fallback`

Suppose the context has two beans sharing the `Sender` interface. A single-valued `Sender` injection point must pick one eligible candidate: `@Primary` can designate the default choice; `@Qualifier("emailSender")` requests a specific role; `@Fallback` from Spring 6.2 lowers a backup bean's priority. These mechanisms intervene in **dependency selection**, without telling Spring which factory method to invoke first.

If a candidate is excluded via `autowireCandidate=false`, precedence annotations do not put it back into the autowire set. If a consumer asks for `List<Sender>`, eligible beans can appear together regardless of which is primary or fallback. This lesson uses SMS chosen as the default to contrast directly with collection order and creation order in section 8's demo.

## 4. `@Order`: Return Order for Collection Injection

If a consumer needs **all** senders, it can inject a collection:

~~~java
public NotificationPipeline(List<Sender> senders) {
    this.senders = List.copyOf(senders);
}
~~~

Spring sorts collections using matching metadata such as `@Order`, `Ordered`, or `@Priority` when the standard annotation is present in a supported location.

~~~java
@Bean("emailSender")
@Order(20)
Sender emailSender() {
    return new NamedSender("EMAIL");
}

@Bean("smsSender")
@Order(1)
Sender smsSender() {
    return new NamedSender("SMS");
}
~~~

When injecting `List<Sender>` from these two beans, the expected result is:

~~~text
[SMS, EMAIL]
~~~

**Lower values have higher precedence in the collection** (for example, 1 comes before 20). That is a **sorting policy**, not an instruction to call the two factory methods in order 1 then 20.

### Do Not Use `@Order` to Replace `@Primary`

A consumer needing a single bean:

~~~java
public NotificationJob(Sender sender) {
    this.sender = sender;
}
~~~

Suppose two beans of the same type carry `@Order(1)` and `@Order(20)`: **do not treat `@Order` as a reliable way to pick a single sender**. Declare `@Primary` on the true default or `@Qualifier` at the injection point.

Spring Javadoc notes that order values can influence priority at **certain injection points**, yet **they do not affect singleton startup order**. The safe practice is to treat `@Order` primarily as **collection ordering**, avoiding business logic that assumes it replaces candidate resolution rules.

### `@Order` on `@Configuration` Classes Means Something Else

You can put `@Order` on a `@Configuration` class, which affects the **evaluation order** of configuration classes being processed. It **does not automatically propagate that order to the `@Bean` methods** inside.

If you want `List<Sender>` ordered, put `@Order` on each target component or `@Bean` method. Never rely on configuration file order or classpath scanning order to establish domain-meaningful collection order.

### `@Order` Does Not Dictate Map Iteration by Default

Spring can inject `Map<String, Sender>`, where keys are bean names. If you want to display bean names deterministically, sort keys or apply an explicit policy. Never assume `@Order(1)` governs every kind of Map traversal or container iteration.

## 5. Initialization Order Follows the Bean Graph, Not Selection Priority

When Spring creates a bean, its **required dependencies** must first be resolved and initialized appropriately. A constructor:

~~~java
public EmailJob(Sender sender) {
    this.sender = Objects.requireNonNull(sender);
}
~~~

expresses **EmailJob depends on Sender**. Under normal bean initialization without cycles, Spring must obtain the matching `Sender` before completing `EmailJob`.

Dependency diagram in the consumer → dependency direction:

~~~mermaid
flowchart LR
    Job["emailJob"] --> Sender["emailSender"]
    Sms["smsSender"] -.->|"initialization dependency"| Email["emailSender"]
    Note["Note: dependency relationship"] --> Meaning["not @Primary/@Order"]
~~~

The arrow from `smsSender` to `emailSender` in the example reflects a case where we **declare an initialization dependency**, such as `@DependsOn("emailSender")`. It does not arise from `smsSender` being primary or having a smaller order number.

### When No Dependency Relationship Exists

Two independent singletons may be created by Spring during context startup, yet **the source-code order of `@Bean` methods or class names must not be treated as a contract**. Some standard setups instantiate non-lazy singletons in definition registration order, but that does not substitute for an explicit dependency relationship and can be altered by the graph, lazy beans, conditions, post-processors, and other bootstrap choices.

**Principle:** if system functionality genuinely requires bean A to initialize before bean B, express that reason via a real dependency or `@DependsOn`, not an incidental order observed in one run.

## 6. `@DependsOn`: Requiring Another Bean to Initialize First

When bean B needs an **initialization side effect** of bean A without directly needing a reference to A in its constructor or properties, you can declare:

~~~java
@Bean("emailSender")
Sender emailSender() {
    return new NamedSender("EMAIL");
}

@Bean("smsSender")
@DependsOn("emailSender")
Sender smsSender() {
    return new NamedSender("SMS");
}
~~~

This is a **snippet** inside a configuration class. When Spring creates `smsSender`, it guarantees that bean `emailSender` is initialized **beforehand**, even though `smsSender` does not hold a field reference to `emailSender`.

**What `@DependsOn` does:**

- Records initialization dependency metadata by **bean name**.
- Forces Spring to create/configure the specified beans before the current bean under the relevant lifecycle rules.
- For singleton destruction, `depends-on` also establishes reverse destruction order: the dependent bean is destroyed before the bean it depends on.
- Useful for side-effect initialization prerequisites not expressed through constructor/property injection, such as a registration prerequisite provided by an infrastructure bean.

**What `@DependsOn` does not do:**

- Does not inject object A into a field of B.
- Does not make A primary or place A first in `List<T>`.
- Does not replace `@Qualifier` when selecting among multiple beans of the same type.
- Does not guarantee B is never invoked before A across all business flows; it constrains **bean lifecycle** only.
- Does not fix circular dependencies. If A depends on B and B depends on A, the graph cannot be initialized normally.
- Does not mean A has finished **all asynchronous tasks** or external system side effects; use an explicit readiness contract when background work exists.

### Prefer a Real Dependency Whenever Possible

If B actually **calls A's API**, use constructor injection:

~~~java
public StartupCoordinator(ReadyState readyState) {
    this.readyState = Objects.requireNonNull(readyState);
}
~~~

This provides a clear Java API and enables plain-Java unit testing. Use `@DependsOn` when **prior initialization is needed without an appropriate dependency reference**, rather than replacing constructor injection with fragile string-based ordering.

**Watch out when renaming:** `@DependsOn("emailSender")` stores the bean name as a String. Renaming the bean without updating the annotation can break context startup. Verify wiring and registration in integration tests.

## 7. `@Lazy`, Singletons, and Prototypes: When Does Creation Actually Occur?

By default, many `ApplicationContext` implementations **eagerly pre-instantiate singleton beans** during context refresh. However, there are important exceptions.

| Bean / Configuration | Typical creation time | What cannot be inferred |
| --- | --- | --- |
| Non-lazy singleton | During context startup/`refresh()` | Will be created in `@Primary`/`@Order` order |
| `@Lazy` singleton not immediately needed by eager beans | Upon first request | Never created or cannot fail |
| `@Lazy` singleton directly required by another non-lazy singleton | May still be created at startup to satisfy the dependency | `@Lazy` always defers unconditionally |
| Prototype | When Spring handles a request to create that bean | Eagerly instantiated like singletons |
| Prototype injected directly into a singleton | Typically resolved once when creating the singleton | Every method call on the singleton gets a fresh prototype |
| `ObjectProvider<T>` | Bean can be looked up on demand via the provider | Automatically enforces business execution order |
| `@DependsOn` | Forces prerequisite initialization before the dependent bean | Selects beans by primary/order |
| Spring 6.2 background initialization (when enabled) | Can run in parallel / out of sync relative to synchronous startup | Guess order from constructor logs |

When code does not wire a lazy bean as a required dependency of an eager singleton, you can verify it is **not** created after `refresh()` and **is** created after `getBean(...)`.

### Where Is `@Lazy` Placed?

`@Lazy` on a bean definition declares lazy initialization policy; this differs from `@Lazy` at an injection point, which may request a lazy-resolution proxy depending on configuration. If an eager consumer needs a lazy bean **directly** during constructor execution, the target bean may still be instantiated early.

Do not use `@Lazy` to hide a dependency cycle or a missing required dependency. Doing so may **merely defer the error**, causing a late runtime failure that is harder to diagnose.

### Scope Is Not Priority

A `@Primary` bean can be singleton, prototype, or another scope. `@Primary` selects the candidate for single injection; **scope controls how instances are supplied**. Picking the right implementation does not guarantee the same object identity across calls if the scope is not singleton.

## 8. Complete Java 17+ Demo: Selecting SMS First While Creating EMAIL First

The program demonstrates **simultaneously**:

- `smsSender` has **`@Primary`** → bare single-valued dependency receives SMS.
- `smsSender` has **`@Order(1)`**, `emailSender` has `@Order(20)` → `List<Sender>` is ordered **[SMS, EMAIL]**.
- `smsSender` has **`@DependsOn("emailSender")`** → even though SMS is first in the collection and primary, the EMAIL bean must initialize before SMS.
- `@Qualifier("emailSender")` on a factory method → specialized consumer still receives EMAIL.
- Bean `lazyReporter` carries `@Lazy` and is not required by any eager bean → after startup it is not yet an instantiated singleton; after lookup it is initialized.

These are **three independent dimensions**: *bean selection*, *list ordering*, and *creation timing*.

Requirements: **JDK 17+**, Maven, and Spring Framework **6.2.19**. The version is pinned for reproducibility, not claimed as the latest. Requires no Spring Boot, HTTP server, or database.

### 8.1. Structure

~~~text
bean-order-vs-initialization/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── BeanOrderVsInitDemo.java
~~~

### 8.2. `pom.xml` File

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bean-order-vs-initialization</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
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
                    <mainClass>demo.BeanOrderVsInitDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Maven resolves the Spring Context modules and transitive JARs. With direct `javac`/`java`, you must include all compile/runtime dependencies, not just a single `spring-context` JAR on the classpath.

### 8.3. `src/main/java/demo/BeanOrderVsInitDemo.java` File

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;
import org.springframework.context.annotation.Lazy;
import org.springframework.context.annotation.Primary;
import org.springframework.core.annotation.Order;

public final class BeanOrderVsInitDemo {
    private BeanOrderVsInitDemo() {}

    public interface Sender {
        String id();
    }

    public record NamedSender(String id) implements Sender {
        public NamedSender {
            Objects.requireNonNull(id);
        }
    }

    public static final class Events {
        private final List<String> events = new ArrayList<>();

        public void record(String name) {
            events.add(name);
        }

        public List<String> snapshot() {
            return List.copyOf(events);
        }

        public boolean before(String earlier, String later) {
            int a = events.indexOf(earlier);
            int b = events.indexOf(later);
            return a >= 0 && b > a;
        }
    }

    public static final class Dashboard {
        private final Sender selected;
        private final Sender specificEmail;
        private final List<Sender> ordered;

        public Dashboard(Sender selected, Sender specificEmail,
                         List<Sender> ordered) {
            this.selected = Objects.requireNonNull(selected);
            this.specificEmail = Objects.requireNonNull(specificEmail);
            this.ordered = List.copyOf(ordered);
        }

        public Sender selectedBean() {
            return selected;
        }

        public String selected() {
            return selected.id();
        }

        public String qualified() {
            return specificEmail.id();
        }

        public String collectionOrder() {
            return ordered.stream().map(Sender::id)
                    .toList().toString();
        }
    }

    public record LazyReporter(String status) {}

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public Events events() {
            return new Events();
        }

        // Declare SMS first in code to avoid relying on source order.
        // @DependsOn is the constraint requiring EMAIL to be created first.
        @Bean("smsSender")
        @Primary
        @Order(1)
        @DependsOn("emailSender")
        public Sender smsSender(Events events) {
            events.record("sms");
            return new NamedSender("SMS");
        }

        @Bean("emailSender")
        @Order(20)
        public Sender emailSender(Events events) {
            events.record("email");
            return new NamedSender("EMAIL");
        }

        @Bean
        public Dashboard dashboard(
                Sender selected,
                @Qualifier("emailSender") Sender specificEmail,
                List<Sender> senders) {
            return new Dashboard(selected, specificEmail, senders);
        }

        @Bean("lazyReporter")
        @Lazy
        public LazyReporter lazyReporter(Events events) {
            events.record("lazy");
            return new LazyReporter("READY");
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            Dashboard dashboard = context.getBean(Dashboard.class);
            Events events = context.getBean(Events.class);
            Sender primary = context.getBean(Sender.class);

            System.out.println("selected=" + dashboard.selected());
            System.out.println("qualified=" + dashboard.qualified());
            System.out.println("collection=" +
                    dashboard.collectionOrder());
            System.out.println("created=" + events.snapshot());
            System.out.println("selectedIsPrimary=" +
                    (dashboard.selectedBean() == primary));
            System.out.println("emailBeforeSms=" +
                    events.before("email", "sms"));
            System.out.println("orderVsCreationDifferent=" +
                    !dashboard.collectionOrder().equals(
                            events.snapshot().stream()
                                    .map(String::toUpperCase)
                                    .toList().toString()));

            System.out.println("lazyBefore=" +
                    context.getBeanFactory()
                            .containsSingleton("lazyReporter"));
            System.out.println("lazyValue=" +
                    context.getBean(LazyReporter.class).status());
            System.out.println("lazyAfter=" +
                    context.getBeanFactory()
                            .containsSingleton("lazyReporter"));
            System.out.println("createdAfterLazy=" + events.snapshot());
        }
    }
}
~~~

### 8.4. Analyzing Each Code Feature

**Bean selection:** `dashboard(Sender selected, ...)` has one unqualified single-valued `Sender` parameter in a context with EMAIL and SMS. `smsSender` carries `@Primary`, so `selected` is SMS. `context.getBean(Sender.class)` also returns SMS. The identity check confirms the same singleton in this context.

**Qualifier-specific dependency:** `@Qualifier("emailSender") Sender specificEmail` resolves to EMAIL even though SMS is primary. The qualifier picks the bean matching the injection point's intent without forcing EMAIL to initialize before SMS; the creation constraint is declared separately.

**Collection ordering:** `@Order(1)` on SMS and `@Order(20)` on EMAIL sort `List<Sender>` as `[SMS, EMAIL]`. Neither source order nor randomness orders the list.

**Creation ordering:** `@DependsOn("emailSender")` on SMS requires EMAIL initialization to complete before the SMS factory runs. Both factory methods record an event in `Events`, producing the trace `[email, sms]`. Both depend on the same `Events` singleton, while `Events` does not record itself.

**Intentionally opposite:** SMS is **primary and first in the List**, yet EMAIL is created **first**. Thus the demo directly disproves “preferred selection means early creation”.

**Lazy:** `LazyReporter` has `@Lazy` on its factory method and no eager bean requires it. `containsSingleton("lazyReporter")` starts as `false`, and turns `true` after `getBean(LazyReporter.class)`. The third event `lazy` proves creation timing differs from the two eager `Sender` beans.

**Deterministic:** the demo uses fixed String labels with no timestamps, randomness, or multi-threaded output. The list/event trace resides in one context, is recorded synchronously, and is solely illustrative; `ArrayList` is not advertised as thread-safe in concurrent apps.

**Java structure:** there is only one public top-level class `BeanOrderVsInitDemo`, with interfaces, records, and config as nested types; package `demo` matches the file path. Java 17 supports records, `List.copyOf`, and `Stream.toList()`.

**`@Configuration(proxyBeanMethods=false)`:** factory methods **do not call each other directly**. Spring resolves dependencies via `@Bean` parameters and `@DependsOn`, so it does not rely on intercepting JavaConfig method calls.

**Lifecycle:** the context closes on exiting `try-with-resources`. The demo does not register destroy callbacks printing to stdout; all expected lines come solely from `System.out.println` in `main`. For a `@DependsOn` singleton with destroy callbacks, Spring also enforces reverse destruction order, though this demo omits destruction logs to avoid confusion with initialization order.

### 8.5. Running via Maven

From the `bean-order-vs-initialization` directory:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

**Exactly 11 stdout lines printed by the program on a successful run:**

~~~text
selected=SMS
qualified=EMAIL
collection=[SMS, EMAIL]
created=[email, sms]
selectedIsPrimary=true
emailBeforeSms=true
orderVsCreationDifferent=true
lazyBefore=false
lazyValue=READY
lazyAfter=true
createdAfterLazy=[email, sms, lazy]
~~~

Lines from `java -version`, `mvn -version`, Maven downloads/logs, or framework logging (if any) do not count toward the **11 `System.out.println` lines printed by `main`**.

**Reading the results without over-interpreting:**

| Line | What it proves | What it does not prove |
| --- | --- | --- |
| `selected=SMS` | `@Primary` selects SMS for the bare type dependency | SMS was created earliest |
| `qualified=EMAIL` | Qualifier picks EMAIL even when SMS is primary | Qualifier controls startup |
| `collection=[SMS, EMAIL]` | `@Order` sorts `List<Sender>` | SMS factory ran before EMAIL factory |
| `created=[email, sms]` | Observed creation order of the 2 `Sender` objects | Every other bean follows this order |
| `selectedIsPrimary=true` | Dashboard holds the exact selected singleton bean | JVM-wide singleton or all scopes |
| `emailBeforeSms=true` | The `@DependsOn` constraint worked | An EMAIL business method always runs before SMS |
| `orderVsCreationDifferent=true` | Collection order and creation order differ | A universal bootstrap schedule applies to all apps |
| `lazyBefore=false` | `lazyReporter` was not instantiated at startup | Lazy always defers even when an eager consumer needs it |
| `lazyValue=READY` | Lookup created `LazyReporter` | Lazy beans lack a lifecycle |
| `lazyAfter=true` | This singleton was created after lookup | Prototypes reside in the singleton registry |
| `createdAfterLazy=[email, sms, lazy]` | Trace records the later lazy initialization event | All background jobs have finished |

### 8.6. Running with `javac`/`java` on Two Operating Systems

If running directly, build a compile/runtime classpath with **all** Maven transitive dependencies:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

Linux/macOS (bash/zsh):

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -cp "$(cat classpath.txt)" \
  -d out src/main/java/demo/BeanOrderVsInitDemo.java
java -cp "out:$(cat classpath.txt)" demo.BeanOrderVsInitDemo
~~~

Windows PowerShell:

~~~powershell
$deps = (Get-Content -Raw classpath.txt).Trim()
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -cp "$deps" -d out src/main/java/demo/BeanOrderVsInitDemo.java
java -cp "out;$deps" demo.BeanOrderVsInitDemo
~~~

On Unix, the classpath separator is `:`; on Windows, `;`. Both commands invoke the same `main`. If `javac` cannot find `org.springframework...`, inspect the Maven POM/classpath before diagnosing candidate resolution or lifecycle.

## 9. Why Should You Not Rely on `@Bean` Order in Source Code?

A few runs might show a bean declared earlier in `@Configuration` being created earlier. That is a **specific observation**, not a contract sturdy enough to coordinate business logic.

Example:

~~~java
@Bean
public Warmup warmup() { ... }

@Bean
public Worker worker() { ... }
~~~

This is an illustrative snippet missing classes and implementations. If `Worker` depends on a side effect of `Warmup` without declaring the relationship, merely placing `warmup()` above `worker()` is **fragile**. Declare:

~~~java
@Bean
@DependsOn("warmup")
public Worker worker() { ... }
~~~

Or better yet, if `Worker` uses the `Warmup` object itself, pass it into the constructor or factory parameter so Spring sees the real dependency.

Registration order can be affected by configuration classes, conditional beans, component scanning, bean factory post-processors, or other extension points. Therefore, **never tie business behavior to the order reflection returns methods**.

### `@Order` on `@Configuration` Differs from Order on `@Bean`

`@Order` at the configuration-class level affects configuration-class processing order, without automatically “cascading” order onto bean methods. To order `List` injection, put `@Order` on the **target bean definition** or implementation type. To force A to initialize before B, declare a **B → A dependency**.

## 10. Initialization and Execution Are Two Different Orders

Even when `@DependsOn("cacheLoader")` ensures the `CacheLoader` bean is **initialized** before the `Job` bean, Spring does not automatically invoke `Job.execute()` after `cacheLoader.load()` unless application logic or a lifecycle contract explicitly calls them.

Distinguish:

- **Construction order:** when the constructor or factory method creates the object.
- **Dependency resolution order:** when Spring creates/retrieves collaborators required by the object.
- **Initialization callbacks:** `@PostConstruct`, `InitializingBean.afterPropertiesSet`, and custom init methods, after injection and before the bean is ready in its normal lifecycle.
- **Runtime method execution order:** controllers, schedulers, event handlers, or application orchestrators calling methods according to business logic.
- **Destruction order:** during context close/shutdown, potentially constrained in reverse by singleton `depends-on`.

**Business example:** if inventory must be checked before charging, write a use case that calls stock then charge with proper error handling and transactions; do not put `@Order(1)` on `StockGateway` expecting the runtime to call it before `PaymentGateway`.

Similarly, `@Primary` only specifies which gateway to pick when selecting one gateway; it does not state **when charging is allowed to happen**. Picking beans and scheduling execution are two distinct responsibilities.

## 11. Destruction Order: `@DependsOn` Works in Reverse for Singletons

With two singleton beans:

~~~java
@Bean("connectionManager")
ConnectionManager manager() { ... }

@Bean("consumer")
@DependsOn("connectionManager")
Consumer consumer() { ... }
~~~

**Illustrative snippet** omitting types. During initialization, `manager` must finish before `consumer`. When the container destroys singleton beans along dependency relationships, Spring ensures **`consumer` is destroyed before `connectionManager`**, allowing `consumer` to clean up while its prerequisite still exists.

This helps with resource ownership, though it does not replace proper `close()`/destroy callbacks when a bean actually owns resources needing release.

Do not assume `@Order` or `@Primary` governs destruction order. Nor should you assume prototype instances get full automatic destroy callbacks simply because they were selected and created by Spring; Spring does not manage prototype destruction the way it manages default singletons.

## 12. Misconceptions to Fix Immediately

| Misconception | Why it is wrong | Right approach |
| --- | --- | --- |
| “`@Primary` means the bean is initialized first” | Primary selects a single-valued candidate | Use dependency graph / `@DependsOn` when init order is needed |
| “`@Order(1)` means the factory method runs first” | Order sorts collections/priority at relevant injection points | Do not use `@Order` to control singleton startup |
| “`@DependsOn` means the dependency will be injected into a field” | Depends-on states only an initialization prerequisite | Inject the object via constructor/factory argument |
| “The first bean in a `List` is always primary” | List ordering differs from single-bean selection | Inspect `@Order` and `@Primary` separately |
| “A bean chosen by `@Qualifier` is created before other beans” | Qualifiers only select candidates | Initialization follows graph/scope/lazy rules |
| “`@Fallback` defers bean creation until needed” | Fallback is a selection precedence policy | Use `@Lazy` when you want a lazy singleton |
| “Adding `@Lazy` prevents startup instantiation altogether” | An eager consumer can force the lazy bean | Check direct dependencies and proxy/injection semantics |
| “Prototypes behave like eagerly created singletons” | Prototypes are created on demand | Understand scope and bean retrieval points |
| “Reordering `@Bean` methods fixes the bug” | Source order is not a lifecycle contract | Declare dependencies explicitly |
| “`@DependsOn` waits for external services to be truly healthy” | Bean init does not equal remote readiness | Build explicit health/readiness contracts |
| “`@Order` on `@Configuration` orders every bean in the class” | Config processing order differs from bean-level collection order | Put `@Order` on the bean target |
| “Once the app starts, every bean has already been created” | Lazy, prototype, and background modes exist | Test creation timing per scope |
| “`@Order` dictates the call order of strategies” | It sorts the injected `List`; code still controls method calls | Write an orchestrator loop over the collection when needed |
| “`@DependsOn` breaks a constructor cycle” | Cyclic graphs have no valid init order | Refactor the cycle and remove hidden mutual dependencies |

### Missing or Extra Beans Are a Separate Problem

If injecting a `Sender` fails because two beans exist with no selection policy, adding `@DependsOn` **does not resolve ambiguity**. If `@DependsOn("emailSender")` reports a missing bean, adding `@Primary` cannot create the missing bean either. Each annotation governs a different relationship; diagnose the real problem before editing.

## 13. Systematic Debugging When Order Is Unexpected

**Step 1 — Clarify which order you are checking.** Are you looking at `List<T>` order, factory event order, lifecycle callbacks, destruction, or business logs?

**Step 2 — Gather the right evidence.** For candidate selection, check the bean identity at an injection point. For `List`, check the order of `Sender::id` inside the `List`. For initialization, record events from constructors/initializers into a single-threaded test collector or inspect the explicit dependency graph.

**Step 3 — Inspect bean definitions.** Which bean names are registered, what are their declared types, and what primary/fallback/qualifier/order metadata do they carry? Are `@Lazy`, scopes, or `@DependsOn` present?

**Step 4 — Check the graph before timestamps.** If B has constructor parameter A, or `@DependsOn("A")`, Spring must process A before B under normal contracts. Without an edge, an incidental log trace gives no guarantee for future runs.

**Step 5 — Distinguish eager from lazy.** A non-lazy singleton usually initializes at refresh; a lazy bean may wait until `getBean`. If a lazy bean is a dependency of an eager bean, check whether it is being forced early.

**Step 6 — Read the exception chain.** `NoUniqueBeanDefinitionException` points to candidate selection; `NoSuchBeanDefinitionException` can indicate a missing prerequisite or bean; `BeanCurrentlyInCreationException` points to a dependency cycle; `BeanCreationException` can wrap initializer errors.

**Step 7 — Fix the right relationship dimension.** Pick one bean → `@Primary`/`@Qualifier`; sort multiple beans → `@Order`; need prerequisite init → real dependency / `@DependsOn`; defer creation → `@Lazy`; business order → orchestration code.

**Step 8 — Write a regression test.** Do not just eyeball console logs when things “look right”; assert a specific invariant in an automated test.

### Tool Selection Matrix

| Requirement | Preferred mechanism | Verification |
| --- | --- | --- |
| Always inject SMS by default | `@Primary` on `smsSender` | `getBean(Sender.class)` or `service.selected.id == SMS` |
| Only EMAIL client uses `emailSender` | `@Qualifier("emailSender")` | Consumer holds the exact named instance |
| Multiple ordered senders | `List<Sender>` and `@Order` on beans | IDs == `[SMS, EMAIL]` |
| Email init must finish before SMS | `@DependsOn("emailSender")` or real dependency | `email` event appears before `sms` |
| Defer reporter until first use | `@Lazy` on bean not required by eager consumers | Not a singleton before lookup; present after |
| Consumer needs A before running B's logic | Explicit orchestration / method calls | Assert call order and failure paths |
| Shut down consumer before prerequisite | Singleton depends-on relationship | Destroy callback event order in a dedicated test |

## 14. Testing Independent Assertions

### Plain-Java Unit Test for Strategy Logic

You can pass fakes/implementations via standard constructor injection:

~~~java
Sender fake = () -> "FAKE";
Dashboard dashboard = new Dashboard(
        fake, fake, List.of(fake));
System.out.println(dashboard.selected()); // FAKE
~~~

This **snippet** must live in a scope accessing the demo's nested types; it is not a standalone Java file. This unit test proves only `Dashboard`'s Java logic, not Spring bean selection.

### Spring Wiring Test

Create a context with `AppConfig.class`, then assert:

- `getBean(Sender.class)` returns the `@Primary` SMS bean.
- The EMAIL bean is still retrievable by name and injected into `specificEmail`.
- `Dashboard.collectionOrder()` returns `[SMS, EMAIL]` per `@Order`.
- Events after refresh contain `email` before `sms` because of `@DependsOn`.
- `LazyReporter` is not yet created right after context refresh when no eager consumer needs it.
- After `getBean(LazyReporter.class)`, `Events` appends `lazy` and the bean is instantiated.

Use test-framework assertions; do not rely on Java's `assert` when `-ea` is off. In serious tests, create a fresh collector per context so events from different runs never mix.

### Useful Negative Tests

**Test 1 — remove `@Primary`:** with two `Sender` beans and a bare single `Sender` injection, ambiguity can arise (unless another rule like qualifier or name matching applies); design the test so name-based shortcuts do not skew the conclusion.

**Test 2 — remove `@DependsOn`:** EMAIL might still appear before SMS in a given run. Yet **the mandatory constraint is gone**; a test must never conclude from an incidental trace that Spring guarantees that ordering.

**Test 3 — change `@Order`:** changing `@Order(1)` to a value larger than EMAIL's changes list ordering **without altering the `@DependsOn` contract**.

**Test 4 — lazy bean needed by eager consumer:** add a non-lazy singleton taking `LazyReporter` in its constructor; `LazyReporter` may now be created during context refresh despite `@Lazy` on its bean definition.

**Test 5 — constructor cycle:** bean A requires B and B requires A; Spring cannot resolve a simple constructor dependency cycle. Fix the graph.

**Test 6 — context shutdown:** add destroy callbacks to both singletons linked by `@DependsOn` to test reverse destruction order. Keep that output separate from the main demo's expected stdout.

## 15. Exercises with Answers

**Exercise 1.** SMS has `@Primary`, EMAIL does not. What does a bare `Sender` injection receive?

**Answer:** SMS, provided no other constraint excludes it from the candidate set; primary governs single-valued selection, not creation timing.

**Exercise 2.** SMS is `@Order(1)`, EMAIL is `@Order(20)`. Which order does `List<Sender>` receive in the demo?

**Answer:** `[SMS, EMAIL]`; lower order values come first when Spring sorts collection injection.

**Exercise 3.** SMS has `@Order(1)` and `@Primary`. Does that guarantee SMS is created before EMAIL?

**Answer:** No. The demo also has `@DependsOn("emailSender")`, so SMS must be created after EMAIL.

**Exercise 4.** Does `@DependsOn("emailSender")` on SMS stop SMS from being primary?

**Answer:** No. `@DependsOn` governs initialization dependency; `@Primary` remains selection metadata.

**Exercise 5.** EMAIL has `@Order(20)`. Why is it still created before SMS in the trace?

**Answer:** Because `@DependsOn` requires EMAIL to initialize before SMS; `@Order` does not dictate factory invocation order.

**Exercise 6.** A consumer has `@Qualifier("emailSender")` even though SMS is primary. What does it get?

**Answer:** EMAIL in the demo; the qualifier narrows candidates to what the injection point requests.

**Exercise 7.** A lazy bean is not referenced by any eager beans. When is it created?

**Answer:** Typically upon first access, not during initial context pre-instantiation.

**Exercise 8.** What happens if a non-lazy singleton directly requires a lazy bean in its constructor?

**Answer:** Spring may have to instantiate the lazy bean at startup to satisfy the eager consumer; a lazy definition is not a promise “never to initialize before direct `getBean`”.

**Exercise 9.** Does `@DependsOn` automatically invoke `Sender.send()` in order?

**Answer:** No. It constrains bean initialization; method execution is determined by application code.

**Exercise 10.** When the context closes, what is the destruction order of singletons linked by `depends-on`?

**Answer:** The dependent bean is destroyed before the prerequisite bean—the reverse of the initialization constraint.

**Exercise 11.** If two singletons have no dependency relationship, should an observed init order be baked into a domain contract?

**Answer:** No. Design an explicit dependency or ready-state if order genuinely matters, rather than relying on incidental registration order.

**Exercise 12.** For a task needing prepare → process → notify steps, is putting `@Order` on three services enough for Spring to execute them in order?

**Answer:** No. Use an orchestrator or service method controlling business sequence, error handling, and retries; `@Order` can only assist by sorting a collection if your own code iterates over that collection sequentially.

## 16. Application Checklist

- [ ] Clearly distinguish **single-bean selection**, **List order**, **initialization order**, and **business execution order**.
- [ ] Use `@Primary` for a sensible default, not as startup priority.
- [ ] Use `@Qualifier` for consumer-specific selection.
- [ ] Use `@Fallback` as a low-priority selection policy, not lazy initialization.
- [ ] Use `@Order` for List/array ordering, not as a lifecycle contract.
- [ ] Place `@Order` in the right spot on `@Bean` methods or target components; do not confuse with `@Configuration` order.
- [ ] Use the dependency graph / constructor injection for collaborators that are actually used.
- [ ] Use `@DependsOn` when prerequisite initialization is needed without a direct reference.
- [ ] Do not rely on `@Bean` source declaration order to enforce an initialization side effect.
- [ ] Do not confuse “bean initialized” with “external service ready” or “business logic executed”.
- [ ] With `@Lazy`, check whether an eager consumer forces early bean creation.
- [ ] With prototype scope, understand beans are not eagerly pre-instantiated like singletons.
- [ ] Know that singleton destruction order is the reverse of `depends-on`.
- [ ] Do not use `@DependsOn` to paper over circular dependencies.
- [ ] Write unit tests for Java logic and integration tests for bean selection, List ordering, and creation events.
- [ ] Run Java 17+ with Maven or `javac`/`java`; compare against the **11 application stdout lines**.
- [ ] When reading logs, ask: “is this an init event, a business log, or a destroy callback?”
- [ ] When errors happen, fix the annotation or mechanism designed for that specific purpose.

**Conclusion:** `@Primary`, `@Qualifier`, and `@Fallback` help Spring **pick the right bean for a dependency**. `@Order` sorts **multiple beans** at collection/relevant injection points. `@DependsOn`, constructor dependencies, `@Lazy`, and scopes govern **when beans are created**. These three decision layers are semantically independent; respecting their boundaries helps you avoid miswired beans, brittle startup assumptions, and broken business sequences.

### Official Spring Documentation

- [Spring 6.2 — Using @Autowired](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired.html)
- [Spring 6.2 — Fine-tuning @Primary / @Fallback](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-primary.html)
- [Spring 6.2 — Using depends-on](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-dependson.html)
- [Spring 6.2 — Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-lazy-init.html)
- [Spring 6.2 — Dependency Injection](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-collaborators.html)
