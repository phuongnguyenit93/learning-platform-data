# `scope`, `lazy-init`, `primary`, and `depends-on` Attributes in Spring Bean Definition

## 1. Four Attributes Controlling Four Different Decisions

Once you know how to define beans with `@Bean` or `@Component`, you need to understand the **metadata** that controls **instance count and lifespan**, **initialization timing**, **dependency selection**, and **initialization order for beans with special relationships**.

| Attribute | Question it resolves | Default / common value | Java configuration |
| --- | --- | --- | --- |
| **`scope`** | In what scope is a bean instance allocated and kept? | `singleton` per Spring container | `@Scope("singleton")`, `@Scope("prototype")` |
| **`lazy-init`** | Is a singleton bean created eagerly at context startup? | Non-lazy singletons are typically eager | `@Lazy` |
| **`primary`** | When multiple beans share a type, which candidate is preferred for **a single dependency**? | No default preferred bean unless declared | `@Primary` |
| **`depends-on`** | Which bean must be **initialized before** the current bean even if not a constructor argument? | Spring relies on actually declared dependencies | `@DependsOn("beanName")` |

These metadata attributes **do not substitute for one another**:

- `@Scope("prototype")` does **not** make a bean a lazy singleton; it changes the scope.
- `@Lazy` does **not** create a new instance on every `getBean`; that relates to scope.
- `@Primary` does **not** set bean creation order and does not change scope.
- `@DependsOn` does **not** select a bean when injecting by interface and **does not automatically inject** the dependent object.

A bean definition can combine multiple attributes, provided there is a real reason. This lesson's example combines `@Lazy` and `@DependsOn` on a service to show the creation order when the service is requested.

## 2. `scope`: Allocation Scope and Lifecycle

### 2.1. `singleton` — Common Default

In Spring, `singleton` means **one bean instance per bean definition per IoC container** (in normal usage). Therefore, retrieving the same singleton bean twice with `getBean` in the same context normally returns the same reference:

~~~java
Object first = context.getBean("catalogService");
Object second = context.getBean("catalogService");
System.out.println(first == second); // true for a singleton bean
~~~

This is an illustrative snippet, assuming `catalogService` is registered in `context`. It is not the classic Singleton pattern holding **one** object across the entire JVM: two separate contexts can hold two different instances, and two separate bean definitions can create two different singletons of the same class.

Because Spring typically pre-instantiates **non-lazy** singletons during `ApplicationContext.refresh()`, constructors and factory methods can be invoked at startup, **before** the first `getBean` call.

**Singleton is not automatically thread-safe.** If a singleton bean holds a `HashMap`, a counter, or mutable state accessed by multiple threads, you still must address concurrency, synchronization, or stateless design. Having a single shared instance makes state handling even more important.

### 2.2. `prototype` — Requesting the Bean Typically Yields a New Instance

A prototype bean is typically created **each time the container receives a request for an instance**:

~~~java
@Bean
@Scope("prototype")
RequestToken requestToken() {
    return new RequestToken();
}
~~~

This is an illustrative example; `RequestToken` is not defined in this snippet. With prototype, two calls to `getBean("requestToken")` normally yield two different objects, though you **should not use a random ID to prove `==`**; compare object identity directly or use a deterministic incrementing ID as in the runnable example in Section 6.

Lifecycle differences to remember:

- Spring manages the instantiation and initialization phase of a prototype.
- Spring **does not automatically invoke full destroy callbacks for every prototype** the way it does for singletons when closing the context. The caller/holder of the object is normally responsible for cleaning up corresponding resources.
- Prototype does not mean "one bean per HTTP request". It refers only to each time the container is asked to create the bean.
- A **prototype dependency injected directly into a singleton** is normally resolved **once when the singleton is created**. Consequently, the singleton retains that same reference on subsequent calls. To obtain a fresh prototype on demand, consider `ObjectProvider<T>` or an appropriate factory.

### 2.3. Other Scopes and Web Contexts

Certain scopes are provided when using a supporting web environment:

| Scope | Typical meaning | Context |
| --- | --- | --- |
| `singleton` | One bean instance per definition/context | Core Container |
| `prototype` | New instance per bean retrieval request | Core Container |
| `request` | Bean lives for one HTTP request | Web-aware application context |
| `session` | Bean per HTTP session | Web-aware application context |
| `application` | Bean bound to ServletContext | Servlet application |
| `websocket` | Bean per WebSocket session | WebSocket integration |

You cannot make `@Scope("request")` work properly simply by using a console `AnnotationConfigApplicationContext`. It requires web scopes to be registered and a valid request context. When injecting a short-lived bean into a longer-lived bean, a **scoped proxy** or provider is sometimes required, rather than merely changing the scope name.

For non-HTTP applications, focus on understanding `singleton` and `prototype` first.

### 2.4. Equivalent XML Syntax

~~~xml
<bean id="accountService"
      class="demo.AccountService"
      scope="singleton"/>

<bean id="requestToken"
      class="demo.RequestToken"
      scope="prototype"/>
~~~

This is an **illustrative XML snippet**; the classes are assumed to exist with suitable constructors. XML and annotations are two ways of providing metadata to the same Core Container, not two different types of containers.

## 3. `lazy-init`: Singleton Initialization Timing

### 3.1. Why Does Lazy Initialization Exist?

`ApplicationContext` normally pre-creates **non-lazy singletons** during `refresh()`. The benefit is that missing beans or initialization errors are typically detected right at startup. However, some beans are very heavy or rarely used, and you want to defer creation cost until first use.

In XML, there is the attribute:

~~~xml
<bean id="reportGenerator"
      class="demo.ReportGenerator"
      lazy-init="true"/>
~~~

In Java configuration, use `@Lazy`:

~~~java
@Bean
@Lazy
ReportGenerator reportGenerator() {
    return new ReportGenerator();
}
~~~

These two snippets are **illustrative**; `ReportGenerator` is not declared here. When not forced into early creation by another eager dependency, `@Lazy` causes a singleton bean to normally be created only on first request, such as `getBean(ReportGenerator.class)`.

**Do not confuse:** `@Lazy` on a **bean definition** defers creating that bean; `@Lazy` at an **injection point** in certain `@Autowired` configurations can create a lazy-resolution proxy for the dependency. The same annotation behaves differently depending on where it is placed.

### 3.2. Common Trap: A Lazy Bean Required by an Eager Singleton

Suppose:

~~~java
@Bean
@Lazy
ExpensiveClient expensiveClient() {
    return new ExpensiveClient();
}

@Bean
PaymentService paymentService(ExpensiveClient client) {
    return new PaymentService(client);
}
~~~

This is illustrative code. `paymentService` is an eager singleton whose constructor/factory method requires `ExpensiveClient`. Spring normally has to create `ExpensiveClient` to supply that argument, **even though that bean is marked `@Lazy`**. Therefore, you cannot look solely at `@Lazy` and assert that the client has definitely not been created after `refresh()`.

If you want to defer access until actual usage, you can design with `ObjectProvider<ExpensiveClient>`, a factory, or a lazy-resolution proxy depending on your needs. Be mindful of lifecycle implications, and note that errors will shift to first usage time.

### 3.3. Lazy Does Not Always Mean Better Performance

Making many beans lazy may reduce startup time, but:

- Configuration errors may surface only when the bean is requested, making them harder to catch early.
- The first request absorbs the creation cost and can incur latency.
- Frequently used beans rarely gain much benefit.
- The dependency graph still dictates actual creation timing.
- It can make init/lifecycle behavior harder to trace if enabled indiscriminately.

Optimize only after knowing real requirements and measuring, rather than marking every bean `@Lazy` merely because it sounds faster.

## 4. `primary`: Selecting a Bean When Multiple Candidates Share a Type

### 4.1. The Type-Based Autowiring Problem

Suppose you have an interface:

~~~java
interface Formatter {
    String format(String value);
}
~~~

And two beans of type `Formatter`:

~~~java
@Bean
Formatter basicFormatter() {
    return value -> "BASIC:" + value;
}

@Bean
Formatter decoratedFormatter() {
    return value -> "DECORATED:" + value;
}
~~~

If a factory method/constructor requires **one** `Formatter` parameter, Spring must decide which bean to choose. Without a clear selection rule, `NoUniqueBeanDefinitionException` can occur.

`@Primary` marks the **preferred candidate** for a single-valued dependency:

~~~java
@Bean
@Primary
Formatter basicFormatter() {
    return value -> "BASIC:" + value;
}
~~~

With exactly one suitable primary candidate, a `Formatter formatter` parameter is injected with `basicFormatter` instead of the other bean.

These snippets are illustrative. The full runnable program in Section 6 uses two concrete implementations and outputs proof of which bean was chosen.

### 4.2. What Can `@Primary` NOT Do?

- **Does not remove/lock out other beans.** Non-primary beans can still be accessed by name or `@Qualifier`.
- **Does not mean running first at startup.** Initialization order is not controlled by `@Primary`.
- **Does not change scope** or create extra singletons.
- **Does not select a single element for collection injection.** Injecting `List<Formatter>`, `Formatter[]`, maps, or streams normally still receives all matching beans, including the primary bean; verify exact ordering rules when using collections.
- **Does not guarantee every ambiguous lookup is resolved** if multiple primaries match or other qualifiers/priorities govern resolution.

If you want a specific implementation at a particular injection point, you can usually use `@Qualifier("decoratedFormatter")`. `@Primary` fits the **default among a group of candidates**, whereas `@Qualifier` expresses an explicit choice at the consumption site. Avoid scattering `@Primary` without a strategy.

### 4.3. Equivalent XML

~~~xml
<bean id="basicFormatter"
      class="demo.BasicFormatter"
      primary="true"/>

<bean id="decoratedFormatter"
      class="demo.DecoratedFormatter"/>
~~~

The XML only illustrates the structure. Both classes must be defined in the project if you want to run it.

## 5. `depends-on`: Initialization Order Before Use

### 5.1. When Is `depends-on` Needed?

Dependencies are usually inferred by Spring from constructor or `@Bean` method parameters:

~~~java
@Bean
OrderService orderService(OrderRepository repository) {
    return new OrderService(repository);
}
~~~

Spring must provide `OrderRepository` before creating `OrderService`. There is no need to add `@DependsOn` just to repeat this relationship.

However, sometimes a bean needs **an initialization action outside its direct dependencies** to execute first—for example, registering a base driver/configuration, loading metadata, or initializing a subsystem needed by a static API. In such cases, use `@DependsOn`:

~~~java
@Bean
@DependsOn("startupGate")
JobRunner jobRunner() {
    return new JobRunner();
}
~~~

This is an illustrative example. Spring ensures **the bean named `startupGate` is initialized before** `jobRunner`. It does not mean Spring automatically passes the `startupGate` instance as a constructor argument to `JobRunner`.

This relationship is declared by **bean name**, not class name. If `startupGate` does not exist in the container, creating `jobRunner` fails with a configuration error; if a `depends-on` cycle exists, the container cannot complete initialization.

### 5.2. Destruction Order for Singletons

For singleton beans with a `depends-on` relationship, Spring can also apply the reverse relationship during destruction: **the dependent bean is destroyed before the bean it depends on**, so the underlying component is not closed prematurely. This rule applies within container-managed lifecycles; do not infer the same for prototypes whose destruction Spring does not fully manage.

**Do not treat `@DependsOn` as a scheduler.** It does not schedule business jobs, perform retries, guarantee ordering for asynchronous events, or replace `@Order` for collection ordering or post-processing.

### 5.3. Equivalent XML

~~~xml
<bean id="jobRunner"
      class="demo.JobRunner"
      depends-on="startupGate"/>

<bean id="startupGate"
      class="demo.StartupGate"/>
~~~

Bean `startupGate` is created before `jobRunner`. Do not confuse the `depends-on` attribute with `constructor-arg ref`: the former enforces init order, while the latter **passes an actual dependency**.

## 6. Runnable Spring 6.2 / Java 17 Example: Testing All Four Attributes

This console example uses no Spring Boot, web server, or database. It intentionally creates **two beans implementing the `Formatter` interface**, a lazy service with `@DependsOn`, and a prototype with an incrementing ID.

### 6.1. Project Structure

Requires JDK 17+, Maven, and downloads `spring-context` on the first run:

~~~text
bean-metadata-demo/
├── pom.xml
└── src/main/java/demo/BeanMetadataDemo.java
~~~

Create `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>bean-metadata-demo</artifactId>
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
                    <mainClass>demo.BeanMetadataDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.2. Complete Java Source Code

Create `src/main/java/demo/BeanMetadataDemo.java`:

~~~java
package demo;

import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;
import org.springframework.context.annotation.Lazy;
import org.springframework.context.annotation.Primary;
import org.springframework.context.annotation.Scope;

public final class BeanMetadataDemo {
    private BeanMetadataDemo() {}

    public interface Formatter {
        String format(String text);
    }

    public static final class MainFormatter implements Formatter {
        @Override
        public String format(String text) {
            return "MAIN:" + text;
        }
    }

    public static final class AlternateFormatter implements Formatter {
        @Override
        public String format(String text) {
            return "ALT:" + text;
        }
    }

    public static final class StartupGate {
        // Demo has no mandatory dependency to pass into TaskRunner.
    }

    public record RequestToken(int id) {}

    public static final class TaskRunner {
        private final Formatter formatter;

        public TaskRunner(Formatter formatter) {
            this.formatter = Objects.requireNonNull(formatter);
        }

        public String run(String id) {
            return formatter.format(id);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        private static final AtomicInteger SEQUENCE = new AtomicInteger();

        @Bean
        @Primary
        public Formatter mainFormatter() {
            return new MainFormatter();
        }

        @Bean
        public Formatter alternateFormatter() {
            return new AlternateFormatter();
        }

        @Bean
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        public RequestToken requestToken() {
            return new RequestToken(SEQUENCE.incrementAndGet());
        }

        @Bean
        @Lazy
        public StartupGate startupGate() {
            System.out.println("CREATE gate");
            return new StartupGate();
        }

        @Bean
        @Lazy
        @DependsOn("startupGate")
        public TaskRunner taskRunner(Formatter formatter) {
            System.out.println("CREATE runner");
            return new TaskRunner(formatter);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            System.out.println("BEFORE runner="
                    + context.getBeanFactory().containsSingleton("taskRunner"));

            TaskRunner runner = context.getBean(TaskRunner.class);
            System.out.println("RESULT " + runner.run("A01"));

            System.out.println("SAME runner="
                    + (runner == context.getBean(TaskRunner.class)));

            Formatter chosen = context.getBean(Formatter.class);
            Formatter alternate =
                    context.getBean("alternateFormatter", Formatter.class);

            System.out.println("PRIMARY " + chosen.format("B02"));
            System.out.println("ALTERNATE " + alternate.format("B02"));

            RequestToken one = context.getBean(RequestToken.class);
            RequestToken two = context.getBean(RequestToken.class);
            System.out.println("TOKENS " + one.id() + "," + two.id());
            System.out.println("TOKEN_DIFFERENT " + (one != two));

            System.out.println("AFTER runner="
                    + context.getBeanFactory().containsSingleton("taskRunner"));
        }
    }
}
~~~

### 6.3. Run Command and Stdout

From the `bean-metadata-demo` directory:

~~~bash
mvn -version
mvn -q compile exec:java
~~~

Exact stdout lines **printed by `BeanMetadataDemo` itself** in order:

~~~text
BEFORE runner=false
CREATE gate
CREATE runner
RESULT MAIN:A01
SAME runner=true
PRIMARY MAIN:B02
ALTERNATE ALT:B02
TOKENS 1,2
TOKEN_DIFFERENT true
AFTER runner=true
~~~

`mvn -version` and Maven/plugins may emit their own version/log lines. The block above describes only the exact output of the `println` statements in the Java demo; it does not promise that the terminal will contain only those lines.

### 6.4. Explaining Why the Output Looks Like This

1. `AnnotationConfigApplicationContext(AppConfig.class)` creates and refreshes the context. The two non-lazy singleton formatters may be created during startup; they do not print anything.
2. `taskRunner` is a `@Lazy` singleton with no eager bean requiring it. Right after refresh, `containsSingleton("taskRunner")` returns `false`, printing `BEFORE runner=false`.
3. When `getBean(TaskRunner.class)` requests creating `taskRunner`, Spring sees `@DependsOn("startupGate")`. Because `startupGate` is also marked `@Lazy` and no earlier bean needed it, **Spring creates the gate first**, printing `CREATE gate`.
4. After the gate, Spring resolves `taskRunner`'s `Formatter` parameter. Two formatters exist, but `mainFormatter` is the sole `@Primary` candidate, so it is selected. The `taskRunner` factory method runs and prints `CREATE runner`.
5. `runner.run("A01")` uses the primary formatter, returning `MAIN:A01`. `TaskRunner` is a singleton, so the second `getBean` call returns the same object: `SAME runner=true`.
6. `getBean(Formatter.class)` returns the preferred `mainFormatter`; an explicit lookup by name `alternateFormatter` still retrieves the second formatter. Hence the two lines `PRIMARY MAIN:B02` and `ALTERNATE ALT:B02`.
7. `RequestToken` has prototype scope, so two calls to `getBean(RequestToken.class)` invoke the factory method twice. The counter in the demo increments from 0 producing IDs 1 then 2, and identity comparison prints `TOKEN_DIFFERENT true`.
8. By the end of the block, the `taskRunner` singleton already exists in the container, so `containsSingleton("taskRunner")` returns `true`.
9. `try-with-resources` closes the Spring context. The demo has no destroy callbacks that print logs, so stdout ends at `AFTER runner=true`.

**Key takeaway of the demo:** the `CREATE gate` line appears **before** `CREATE runner` because of `depends-on`. Neither appears at startup because both beans are lazy and no eager bean forces their initialization.

Do not infer from the output that every bean is created strictly in source-code declaration order inside `AppConfig`: Spring only guarantees the relevant dependency/configuration relationships; unrelated ordering must not be relied upon as business logic.

## 7. Combining the Four Attributes in Real Applications

### 7.1. A Singleton Service Needing a Fresh Prototype per Task

If a singleton `TaskRunner` needs a fresh `RequestToken` on each invocation, do **not** inject `RequestToken` directly into its constructor and expect it to change automatically.

Instead, you can inject `ObjectProvider<RequestToken>`:

~~~java
import org.springframework.beans.factory.ObjectProvider;

final class ProcessingService {
    private final ObjectProvider<RequestToken> tokens;

    ProcessingService(ObjectProvider<RequestToken> tokens) {
        this.tokens = tokens;
    }

    void process() {
        RequestToken token = tokens.getObject();
        // Use the fresh token for the current processing run.
    }
}
~~~

This is an **illustrative snippet**, using the `RequestToken` record from Section 6; it is not a standalone runnable file. `ObjectProvider.getObject()` requests a bean from the container when invoked, so for a prototype it normally receives a new object.

### 7.2. Choosing a Primary While Still Accessing Another Bean

An application might have email and SMS beans sharing an interface, marking email as the `@Primary` default. Yet when a specific use case explicitly requires SMS, `@Qualifier("smsNotifier")` at the injection point makes the intent clear. Do not use `@Primary` to decide per-request business logic, such as selecting a channel from user input; that calls for a separate strategy/router design.

### 7.3. Do Not Confuse `depends-on` with Dependency Injection

If a service needs to call methods on `ClientPool`, declare `ClientPool` as a constructor or factory method parameter. `@DependsOn("clientPool")` **does not supply a `ClientPool` reference**. It only enforces prior initialization. Use `depends-on` when there is an **ordering constraint outside normal injection relationships**, and document why.

### 7.4. Lazy on Beans with Initialization Side Effects

Consider:

- Does a bean doing heavy work at startup genuinely need to be created immediately?
- If deferred, will the first request suffer unacceptable latency or exceptions?
- Does another eager singleton directly depend on this bean?
- Could you design background initialization, post-startup preloading, or a factory/provider instead of generic lazy marking?

Do not place core business side effects inside a constructor merely to leverage `depends-on`; business execution order belongs in explicit methods or proper lifecycles, not hidden inside bean creation.

## 8. Common Misconceptions and Errors

| Misconception / Error | Correct Understanding or Handling |
| --- | --- |
| "`singleton` means one object for the whole JVM." | Spring's singleton is per bean definition within **each container**. |
| "`singleton` is always thread-safe." | Scope does not add synchronization; design state/concurrency yourself. |
| "`prototype` is destroyed when closing the context." | Spring generally does not manage full destroy callbacks for prototypes. |
| "Injecting a prototype into a singleton gives a new prototype per method call." | Injection typically happens once; use a provider/factory when needed. |
| "`@Lazy` guarantees the bean is not initialized at startup." | An eager dependency can force it to be created earlier. |
| "`@Lazy` is equivalent to `@Scope("prototype")`." | One attribute controls timing; the other controls scope. |
| "`@Primary` causes the bean to initialize first." | Primary governs resolution priority, not init order. |
| "`@Primary` makes other beans of the same interface disappear." | They still exist and can be retrieved by name/qualifier. |
| "Two primaries of the same type will surely pick one." | It can still be ambiguous; selection configuration must be unambiguous. |
| "`@DependsOn` automatically passes the dependency to the constructor." | No; it enforces init order by bean name. |
| "`@DependsOn` is the standard way to fix circular dependencies." | No; it can create or expose dependency cycles, requiring redesign. |
| "`@DependsOn` controls all events/jobs in order." | No; it only affects the lifecycle of the corresponding beans. |
| "Request/session scope works in a console context." | Requires web-aware scopes and an active request/session context. |
| "Prototype and singleton always have the same destruction mechanism." | Prototype destruction lifecycle differs from singleton. |
| "Lazy bean errors always show up at startup." | They may surface only the first time the bean is requested. |
| "Having `@Bean` means a bean already exists." | The configuration class must be registered/scanned and metadata processed by the container. |

### Reading Related Errors

- `NoSuchBeanDefinitionException`: `@DependsOn` points to a misspelled bean name, or the dependency is not registered.
- `NoUniqueBeanDefinitionException`: multiple candidates for a single dependency without disambiguation; consider `@Primary` or `@Qualifier`.
- `BeanCreationException`: constructor/factory/lifecycle failure, which may happen later for lazy beans.
- `BeanCurrentlyInCreationException` or circular dependency errors: the bean creation graph has an unresolvable cycle.
- `ScopeNotActiveException`: attempting to access a scoped bean outside an active scope context.

When debugging, inspect the **root cause** and bean name in the stack trace. Do not try to patch around a broken graph design by switching everything to prototype or sprinkling `@Lazy` everywhere.

## 9. Self-Check Exercises (with Answers)

**1.** Two calls to `getBean("catalogService")` return the same reference. Can you conclude there is only one object across the entire JVM?

**Answer:** No. For a singleton, it is normally the same bean instance within the **current context**. Another context or another bean definition can create a different instance.

**2.** A `@Lazy` bean is injected directly into an eager singleton. Will it always wait until called before being created?

**Answer:** No. To instantiate the eager singleton, Spring may have to resolve and create the lazy dependency beforehand. If you want to defer it, intentionally use a provider or lazy proxy.

**3.** Two beans implement the `Formatter` interface; one has `@Primary`. Can you still retrieve the other bean?

**Answer:** Yes. You can retrieve it by name or using an explicit `@Qualifier`. Primary mainly resolves a single injection point when multiple candidates exist.

**4.** A `jobRunner` bean has `@DependsOn("startupGate")`. Does `JobRunner` automatically receive a `StartupGate` parameter?

**Answer:** No. That is an initialization order constraint. If you need the object to invoke methods on it, declare the dependency via constructor/factory parameter.

**5.** Why does `CREATE gate` appear before `CREATE runner` in the demo?

**Answer:** `taskRunner` has `@DependsOn("startupGate")`. When the runner is requested, Spring creates the gate first and only then creates the runner.

**6.** Why do two calls to `getBean(RequestToken.class)` produce IDs 1 and 2?

**Answer:** The `RequestToken` bean is prototype-scoped, so the factory is invoked for each request. `AtomicInteger` assigns incrementing IDs within a single JVM run of the demo. The two instances differ under `==`.

**7.** If a singleton service has a prototype constructor parameter `RequestToken token`, does every call to `service.run()` get a new token?

**Answer:** Not under ordinary direct injection. The singleton keeps the instance injected when it was created; use `ObjectProvider<RequestToken>` or a factory if you want a fresh instance per execution.

**8.** Given singleton A `@DependsOn("B")`, if both have destroy callbacks, is B destroyed before A?

**Answer:** Not in Spring's managed singleton dependency destruction mechanism: the dependent bean **A is normally destroyed before B**, keeping B available while A cleans up.

**9.** Should you use `@Primary` to choose a payment method based on order type at runtime?

**Answer:** Not directly. Primary is resolution metadata for selecting a default candidate when wiring beans; runtime selection based on business data requires a strategy/router or suitable architecture.

## 10. Checklist for Intentional Bean Metadata Usage

- [ ] Beans are registered via `@Configuration`/`@Bean`, component scanning, or bean definitions in the right context.
- [ ] Identify which beans should be stateless singletons and which need short-lived instances.
- [ ] Do not store unsafe mutable state in singletons accessed by multiple threads.
- [ ] For prototypes, have an ownership/resource cleanup plan when needed.
- [ ] If a singleton needs multiple prototypes over time, choose a provider/factory rather than expecting direct injection to swap automatically.
- [ ] Place `@Lazy` only when genuinely needed to defer creation and after checking eager dependencies.
- [ ] Have a plan to observe errors that may surface at first use for lazy beans.
- [ ] When multiple beans share a type, specify primary/qualifiers according to clear rules.
- [ ] Do not treat primary as an init-scheduling mechanism or as excluding other beans.
- [ ] Specify `@DependsOn` using the **exact bean name**, and only when initialization order cannot be expressed via direct dependencies.
- [ ] Understand destruction order for dependent singletons and do not blindly apply it to prototypes.
- [ ] Do not use `@DependsOn` as a substitute for passing dependencies in constructors.
- [ ] Test output/lifecycle in a small application before applying to a large graph.
- [ ] When expanding to request/session scopes, use an appropriate web-aware context.
- [ ] Do not equate these four attributes with AOP proxies, transaction management, or HTTP routing.

## 11. Spring Reference Documentation

- [Bean scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Lazy-initialized beans](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html)
- [Using depends-on](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-dependson.html)
- [Classpath scanning, @Scope and @Primary](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html)

**Conclusion:** `scope` determines **instance lifespan/allocation**, `lazy-init` determines **when to create** (subject to the dependency graph), `primary` selects the **preferred candidate** for a dependency, and `depends-on` forces **initializing another bean beforehand**. Knowing the exact boundaries of each attribute helps design predictable bean graphs, avoid lifecycle bugs, prevent autowiring ambiguity, and keep business flows out of metadata.