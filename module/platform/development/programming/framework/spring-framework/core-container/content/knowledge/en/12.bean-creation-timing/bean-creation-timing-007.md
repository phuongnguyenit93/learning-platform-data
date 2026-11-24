# Distinguishing `@Order`, `@DependsOn`, and Bean Definition Order in Spring Framework

## 1. Three Different Kinds of "Order"

In the Spring IoC Container, many questions are phrased as "which bean runs first?"; however, at least **three independent concerns** are commonly lumped together:

1. **Order of beans used inside a collection:** when injecting `List<Handler>`, which handler comes first so the pipeline calls it first?
2. **Initialization and destruction order of beans:** when a singleton has a side effect creating infrastructure, which bean must finish initializing before another bean?
3. **Registration/declaration order of bean definitions:** which `@Bean` method or XML `<bean>` the developer wrote first in a source file, and in what order the BeanFactory recorded definitions?

These three concerns have different mechanisms and guarantees:

| Question | Appropriate mechanism | What not to infer |
| --- | --- | --- |
| What order does an injected `List<Stage>` have? | `@Order`, `Ordered`, `@Priority` in supported contexts | Do not infer that target beans were initialized in list order |
| Bean B must **be initialized after** bean A? | Real dependency injection or `@DependsOn("A")` | `@Order(1)` on A does not guarantee A is created before B |
| B must close before A at shutdown? | Dependency/`@DependsOn` relationship on singletons, proper lifecycle | `@Order` used for list sorting does not define destruction order |
| Without `@Order`, what order does a list have? | Normally the registration order of target bean definitions | Not a long-term guarantee when scanning/importing/refactoring changes |
| What if `@Bean first()` is written above `second()`? | Merely order in source code | Not an init-before contract |
| Need to start/stop services in phases? | `SmartLifecycle.getPhase()` and dependency graph | Do not use `@Order` to replace `SmartLifecycle` |

In this lesson, `@Order` belongs to `org.springframework.core.annotation`, while `@DependsOn` belongs to `org.springframework.context.annotation`. The two annotations are not alternate spellings of the same feature.

**Key takeaway from Spring Framework 6.2:** `@Order` is used for ordering at multiple consumption points (especially collection injection), and **does not control singleton startup order**. `@DependsOn` establishes a guaranteed relationship between bean definitions: the dependency is initialized before the dependent and, for singletons, the dependent is destroyed before the dependency.

Learning objectives:

- Distinguish the phases **bean definition registration**, **bean instance initialization**, **injection collection sorting**, **init/start**, and **destroy/stop**.
- Use `@Order` properly on component classes/`@Bean` methods; understand that lower numbers have higher precedence.
- Use `@DependsOn` on the bean that requires the dependency, by **bean name**, not class name.
- Know the registration-order fallback for collections without order metadata and the limits of that mechanism.
- Distinguish `@Order` on a `@Configuration` class from `@Order` on **individual `@Bean` methods**.
- Understand that `@Primary`/`@Qualifier` and `@Priority` are not completely synonymous with `@Order`.
- Write and run a Java 17+ demo with Spring Context 6.2, complete with assertions and stdout.
- Test configuration errors, shutdown order, event pipelines, and effects of lazy/prototype scopes.

## 2. Timing Model of the Spring Container

A simplified diagram:

```text
ApplicationContext is configured
             |
             v
Read @Configuration / @Component / XML / imports
             |
             v
Register BeanDefinition and related metadata
  name, scope, lazy, dependsOn, qualifiers, order...
             |
             v
Process BeanFactoryPostProcessor / bean metadata
             |
             v
Pre-instantiate eligible non-lazy singleton beans
   respecting the dependency graph
             |
             v
Supply dependencies to consumers
  + sort List<T>/T[] at appropriate injection points
             |
             v
Invoke business methods, SmartLifecycle.start(), ...
             |
             v
Close context
   lifecycle stop, singleton destruction ...
```

The diagram is not the entire Spring lifecycle: bean post-processors, AOP proxies, factory methods, custom scopes, and Spring 6.2 background initialization can make details more complex. Yet a crucial distinction is:

- **Registration**: the container knows a bean definition *exists*; the instance may not have been created yet.
- **Instantiation/initialization**: the container creates the object and completes initialization.
- **Collection resolution**: the container selects and sorts candidate objects for an injection point.
- **Invocation**: the application invokes methods in the order decided by the application.
- **Destruction**: the container releases managed singletons when the context closes per dependency/lifecycle rules.

You can have a `List<Stage>` ordered `A, B, C` while constructor or static init event order is not `A, B, C` at all. Never equate "sorted list" with "startup order".

## 3. `@Order`: Used When a Set of Elements Needs Order

Annotation:

```java
import org.springframework.core.annotation.Order;

@Order(-100)
class SecurityFilter implements FilterStep {
    // ...
}
```

This is an **illustrative excerpt**; the `FilterStep` interface and appropriate method bodies are required to compile. The meaning of `@Order(-100)` is declaring an **order value** used when Spring or related infrastructure sorts elements.

### 3.1. Smaller Numbers Come First

Numeric order:

```text
@Order(-10)  → earlier
@Order(0)    → middle
@Order(20)   → later
@Order(100)  → even later
```

Per the `Ordered` contract, **smaller values have higher priority** in sorting. Spring defines two constants:

```java
Ordered.HIGHEST_PRECEDENCE   // Integer.MIN_VALUE
Ordered.LOWEST_PRECEDENCE    // Integer.MAX_VALUE
```

These are constant reference examples; import `org.springframework.core.Ordered` when writing standalone Java.

`@Order` defaults to `Ordered.LOWEST_PRECEDENCE`. If multiple elements have no order directive or share the same order value, do not build business logic relying on an uncontracted tie-breaking order; you may need explicit rules at the application layer.

### 3.2. Example Injecting `List<Step>`

Suppose we have:

```java
public interface Step {
    String code();
}
```

And three implementation/component beans:

```java
@Component
@Order(30)
class StepValidate implements Step {
    public String code() { return "validate"; }
}

@Component
@Order(-10)
class StepAuthenticate implements Step {
    public String code() { return "authenticate"; }
}

@Component
@Order(10)
class StepEnrich implements Step {
    public String code() { return "enrich"; }
}
```

These two excerpts are illustrative snippets; imports and component scanning are needed for the beans to exist. With a consumer:

```java
@Component
class Pipeline {
    private final List<Step> steps;

    Pipeline(List<Step> steps) {
        this.steps = steps;
    }
}
```

Spring can inject `steps` in the order `authenticate, enrich, validate` because `-10 < 10 < 30`.

**This is element order in the collection at the injection point.** The container is not required to initialize `StepAuthenticate` before `StepEnrich` before `StepValidate` merely because they carry `@Order`.

### 3.3. Using `@Order` on a `@Bean` Method

Some types do not carry `@Component`, or you want multiple bean definitions returning the same implementation class with different priorities:

```java
@Bean("secondStep")
@Order(20)
Step secondStep() {
    return new NamedStep("second");
}

@Bean("firstStep")
@Order(0)
Step firstStep() {
    return new NamedStep("first");
}
```

This snippet requires `Step`, `NamedStep`, and `@Bean` imports. When injecting `List<Step>`, Spring 6.2 reads `@Order` on the **target `@Bean` methods** and can order `first` before `second`.

This matters if two bean definitions share the same class: `@Order` on the class cannot express distinct priorities for each bean definition, whereas method annotations can.

### 3.4. `Ordered` Interface When Order Is Computed Per Instance

Instead of hard-coding annotation metadata, an object can do:

```java
public final class ConfigurableStep
        implements Step, Ordered {

    private final String code;
    private final int order;

    public ConfigurableStep(String code, int order) {
        this.code = code;
        this.order = order;
    }

    @Override
    public String code() {
        return code;
    }

    @Override
    public int getOrder() {
        return order;
    }
}
```

Requires imports for `Ordered` and `Step`. When infrastructure uses `AnnotationAwareOrderComparator`/order-aware sorting, the value from `Ordered.getOrder()` can be used to sort elements. This is useful when configuring order at the bean instance level rather than a fixed annotation on the class.

**Limitation:** implementing `Ordered` does not make Spring automatically invoke business method `execute()` in order. A consumer/pipeline must actually iterate over the ordered collection, or specific infrastructure must apply that comparator.

### 3.5. `@Order` on `@Configuration` Does Not Propagate Down to `@Bean` Methods

This is a distinction explicitly stated in Spring 6.2 documentation:

```java
@Configuration
@Order(-100)
class AlphaConfiguration {

    @Bean
    Step alphaStep() {
        return new NamedStep("alpha");
    }
}

@Configuration
@Order(100)
class BetaConfiguration {

    @Bean
    Step betaStep() {
        return new NamedStep("beta");
    }
}
```

The illustrative code above omits imports/types. `@Order` on **configuration classes** can affect **evaluation order across the set of configuration classes**, without automatically assigning `-100` and `100` to the `Step` beans produced by factory methods.

To sort `List<Step>` by specific values, place `@Order` on **each `@Bean` method** (or on target classes/`Ordered` appropriately).

**Do not infer**: Alpha config evaluated first → `alphaStep` bean definitely created first → list ordered that way. Those are three separate layers.

## 4. Collection Injection Without `@Order`

The Spring Reference states that for typed array/list injection, if candidates have no `Ordered`, `@Order`, or `@Priority` driving order, the order normally follows **registration order of target bean definitions** in the container.

Example:

```java
@Bean("eastStep")
Step eastStep() { return new NamedStep("east"); }

@Bean("westStep")
Step westStep() { return new NamedStep("west"); }
```

Without order metadata, Spring uses registration order as a fallback for the List. However, **do not treat source line order as an immutable contract**. Registration order can change when:
- adding `@Import` or changing the composition root;
- changing component scan packages/filtering;
- adding a `BeanDefinitionRegistryPostProcessor`/registrar;
- migrating from XML to JavaConfig or changing build packaging;
- changing dependency/framework versions;
- changing how programmatic registration is invoked.

**Recognize four distinct kinds of order**:

| Name | Meaning | When used? |
| --- | --- | --- |
| Source declaration order | Where a method/class/`<bean>` appears in source | Human reading and maintenance |
| Bean definition registration order | Order in which container records target bean definitions | Fallback for unordered List/array candidates |
| Bean instance creation order | When constructors/factory/init actually execute | Dependency graph, eager/lazy, background/bootstrap |
| Consumer invocation order | Sequence in which pipeline calls Steps | Consumer logic and sorted collection |

There is no general rule saying "source declaration = registration = instantiation = invocation".

### 4.1. Does XML `<bean>` Top-to-Bottom Guarantee Init Order?

Do not rely on **tag position** to require a side effect to happen first. In some typical configurations, non-lazy singleton pre-instantiation may appear close to registration order; however, the dependency graph, lazy beans, FactoryBeans, imports, BeanPostProcessors, and other mechanisms can alter the order.

If Bean B must wait for Bean A to finish initialization, declare the relationship properly using `<ref>`/constructor dependency or `depends-on`, rather than moving XML tags around.

### 4.2. Java Reflection/Method Declaration Order Is Not a Scheduling API

In JavaConfig, Spring analyzes annotations and factory methods to register bean definitions. Do not build logic solely on which line is written first inside a `@Configuration` class. Java source method order is not an API contract constraining initialization order of managed beans.

### 4.3. XML Import/Java Import Can Change the Candidate Set

When a configuration imports more beans, the total candidate count and registration order can change. If the list is a **critical pipeline** (security, validation, routing), use `@Order` or an explicit order contract. If stage order does not affect business logic, do not add order values just because it feels like an order is needed.

## 5. `@DependsOn`: Initialize Prerequisite First, Destroy Dependent First

`@DependsOn("bootstrap")` placed on bean `worker` expresses a **lifecycle** relationship, independent of handler order in a collection:

```java
@Bean("worker")
@DependsOn("bootstrap")
Worker worker() {
    return new Worker();
}
```

The name `bootstrap` must be a valid bean name or alias. When `worker` is initialized, Spring must create and initialize the prerequisite first; for two managed singletons with destroy callbacks, `worker` is destroyed before `bootstrap`.

```text
INIT:    bootstrap -> worker
DESTROY: worker    -> bootstrap
```

XML uses `<bean id="worker" depends-on="bootstrap" ... />`. `@DependsOn` **does not inject an object**: if `Worker` needs to use the `Bootstrap` instance itself, a constructor or factory-method parameter is the proper declaration. Class-level `@DependsOn` is processed along the component-scanning path; if the class is registered directly via XML, use XML `depends-on`.

`@DependsOn({"bootstrap","metrics"})` ensures both prerequisites exist before `worker`, yet the listing order in the array should not be treated as a business workflow forcing `bootstrap` to run before `metrics`. Also do not use it to defer beans: an eager dependent can pull a lazy prerequisite into startup.

The previous lesson on `@DependsOn` covered declaration and diagnostics in detail. In this comparative lesson, the point to verify is that **`@DependsOn` establishes init/destroy relations, whereas `@Order` only sorts a collection of beans**. Both requirements can coexist on one component and must be tested separately.

## 6. Why Doesn't `@Order` Replace `@DependsOn`?

Suppose there is a pipeline with two `Handler`s:

```java
@Component
@Order(-100)
class BootstrapHandler implements Handler {
    // ...
}

@Component
@Order(100)
class AuditHandler implements Handler {
    // ...
}
```

The `List<Handler>` collection can place `BootstrapHandler` before `AuditHandler`. However, Spring is **not required** to invoke `BootstrapHandler`'s constructor/init before `AuditHandler` merely because of `@Order(-100)`.

In an application using singleton beans:
- when the context pre-instantiates beans, order is still governed by the graph and bootstrap operations;
- `@Order` may only be read when the BeanFactory resolves candidates for a `List`;
- if `AuditHandler` has a `@PostConstruct` side effect needing `BootstrapHandler`'s infrastructure to already be ready, `@Order` does not satisfy that requirement.

If init-before is needed, use:

```java
@Component
@DependsOn("bootstrapHandler")
class AuditHandler implements Handler {
    // ...
}
```

This solution assumes bean name `bootstrapHandler` is registered properly per naming convention or explicit designation. You can still keep `@Order` **simultaneously** to control position in the `List` when business logic requires it.

### 6.1. Needing Both Mechanisms at the Same Time

A system may need:
- authentication infrastructure initialized before the audit handler;
- the authentication handler executed before the audit handler in the request pipeline.

In that case, **two separate contracts** are needed:
- `@DependsOn` or a DI edge for the initialization graph;
- `@Order` for collection processing order.

One annotation alone cannot substitute for the other.

### 6.2. List Order Does Not Mean One Handler Is Called First

If a consumer does not use `List<Handler>` and instead looks up beans by name and invokes them directly, `@Order` does not force callers to invoke handlers in order.

Conversely, a consumer that receives an ordered list yet deliberately calls `list.get(2)` first is not prevented by Spring either. The framework sorts the **collection**, while the application decides **invocation**.

## 7. `@Order`, `@Priority`, `Ordered`, `@Primary`, and `@Qualifier`

These names are easily confused, yet solve different problems:

| Mechanism | Primary purpose | Example |
| --- | --- | --- |
| `@Order(5)` | Declare sort order when processing a collection of elements | Pipeline List |
| `Ordered#getOrder()` | Return order value from a bean instance | Plugin order from config |
| `@Priority(5)` (Jakarta) | Priority in ordering; has additional semantics in certain single-bean selection contexts | Framework-level prioritization |
| `@Primary` | Choose default when multiple beans share a type for a **single injection point** | A default `DataSource` |
| `@Qualifier("east")` | Narrow candidate set for a dependency | Select a specific bean |
| `@DependsOn("bootstrap")` | Init-before / destruction-after relation | Resource initialization |
| Registration order | Fallback sorting for List/array lacking order metadata | Consequence of how definitions are registered |

### 7.1. `@Order` Does Not Default to Selecting a Single Bean

Two beans both implement `PaymentGateway`:

```java
@Bean
@Order(-100)
PaymentGateway fastGateway() { return new FastGateway(); }

@Bean
@Order(100)
PaymentGateway safeGateway() { return new SafeGateway(); }
```

If a consumer requests **a single** `PaymentGateway` without a qualifier:

```java
@Bean
CheckoutService checkoutService(PaymentGateway gateway) {
    return new CheckoutService(gateway);
}
```

Do not infer that Spring will automatically choose `fastGateway` merely because of `@Order(-100)`. `@Order` mainly handles **order within a set of candidates**. For a single dependency, `@Primary`, `@Qualifier`, or an appropriate naming policy may be needed. `@Priority` can have additional semantics when selecting a single element, so it should not be equated with `@Order` either.

### 7.2. `@Primary` Does Not Sort Lists

If one of three handlers has `@Primary`, that does not automatically move that handler to the front of `List<Handler>`. When the injection point is a collection, Spring typically gathers all eligible candidates and applies separate order metadata.

### 7.3. Qualifiers Filter Candidates Before/Alongside Ordering

A `List` injection point annotated with `@Qualifier("critical")` can receive only the group of handlers carrying the matching qualifier, and then sort order within **that filtered subset**.

Inspect the specific annotations and bean definitions: `@Qualifier` is not ordering, and `@Order` is not filtering.

### 7.4. `Set` and `Map`: Read the Contract Before Promising Order

The Spring reference explicitly describes order sorting for **arrays** and **typed Lists**. `Map<String, Handler>` provides bean names as keys and beans as values. Do not build business pipelines assuming every traversal of a `Set` or `Map` honors `@Order` the same way as a `List`.

If order is business-critical, inject `List<Handler>`, or explicitly produce an ordered sequence from map values using a comparator in code, and write tests for that contract.

## 8. XML Comparison Example

XML beans:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="worker"
          class="example.Worker"
          depends-on="bootstrap"/>

    <bean id="bootstrap"
          class="example.Bootstrap"/>
</beans>
```

This is an **illustrative configuration**: `example.Worker`/`example.Bootstrap` must exist. `Worker` is written before `Bootstrap` in XML, yet dependency metadata forces `Bootstrap` to be initialized before `Worker`. Close equivalent:

```java
@Configuration(proxyBeanMethods = false)
class ExampleConfiguration {

    @Bean("worker")
    @DependsOn("bootstrap")
    Worker worker() {
        return new Worker();
    }

    @Bean("bootstrap")
    Bootstrap bootstrap() {
        return new Bootstrap();
    }
}
```

This is an illustrative Java snippet; imports/types are needed. `@DependsOn` applies on the `worker()` factory method; the configuration does not need to call `bootstrap()` directly from `worker()` to create the ordering dependency.

### 8.1. XML Declaration Order Does Not Create a Dependency Edge

If `depends-on="bootstrap"` is removed and `Worker` does not inject `Bootstrap`, only two independent bean definitions remain. Whether `Worker` sits before or after `Bootstrap` in the file might alter **observations** in one specific version/loading mode, yet that is not a good dependency contract to guarantee side effects.

### 8.2. When a Bean Has Aliases, `depends-on` Can Use a Registered Name

If `bootstrap` has alias `initSubsystem`, `depends-on="initSubsystem"` can resolve the valid alias name. However, dependency naming should stay stable and test-protected; renaming beans/aliases during migrations can break `@DependsOn`.

### 8.3. Do Not Force Order with `<import>` File Order

Splitting configuration into `00-bootstrap.xml` and `10-worker.xml` does not replace dependency graph logic. When importing multiple XMLs, file load order can create the illusion that "bootstrap is always first". Use `depends-on` or constructor/reference injection for real requirements.

## 9. Runnable Demo: Java 17+ and Spring Framework 6.2

This demo separates both concepts inside a single application context:

- **Collection order:** `@Order` placed on three `@Bean` methods: stage `first` comes before `middle` and `last` even though `lastStage` is written first.
- **Initialization/destruction order:** bean `worker` has `@DependsOn("bootstrap")`. Neither bean injects a reference to the other; the goal is proving independent ordering metadata.
- **Bean definition order inspection:** registered names can be inspected to confirm registration is not itself a creation contract.
- **Assertions:** instead of merely printing logs and guessing, the program verifies the sorted `List`, created-before, and destroyed-after contracts.

No Spring Boot, database, HTTP, or external service is needed. The demo uses a single Java file with nested types and a simple Gradle setup.

### 9.1. Project Structure

```text
bean-ordering-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── BeanOrderingDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'bean-ordering-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

application {
    mainClass = 'BeanOrderingDemo'
}
```

JDK 17+ and a Gradle version supporting that JDK are sufficient for source using records, `List.of`, and `AnnotationConfigApplicationContext`.

### 9.2. Complete Java Code

Save `src/main/java/BeanOrderingDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;
import org.springframework.core.annotation.Order;

public class BeanOrderingDemo {

    public interface Stage {
        String label();
    }

    public record NamedStage(String label) implements Stage {
    }

    public record Pipeline(List<Stage> stages) {
        public List<String> labels() {
            return stages.stream()
                    .map(Stage::label)
                    .toList();
        }
    }

    public static final class Events {
        private final List<String> values = new ArrayList<>();

        public void add(String event) {
            values.add(event);
        }

        public List<String> snapshot() {
            return List.copyOf(values);
        }
    }

    public static final class Bootstrap implements AutoCloseable {
        private final Events events;

        public Bootstrap(Events events) {
            this.events = events;
            events.add("init:bootstrap");
        }

        @Override
        public void close() {
            events.add("destroy:bootstrap");
        }
    }

    public static final class Worker implements AutoCloseable {
        private final Events events;

        public Worker(Events events) {
            this.events = events;
            events.add("init:worker");
        }

        @Override
        public void close() {
            events.add("destroy:worker");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class DemoConfig {

        // Method declared first, but not permitted to initialize
        // before the bean named "bootstrap".
        @Bean(name = "worker", destroyMethod = "close")
        @DependsOn("bootstrap")
        Worker worker(Events events) {
            return new Worker(events);
        }

        @Bean(name = "bootstrap", destroyMethod = "close")
        Bootstrap bootstrap(Events events) {
            return new Bootstrap(events);
        }

        @Bean
        Events events() {
            return new Events();
        }

        // The source order of these factory methods is purposely
        // different from the desired order in List<Stage>.
        @Bean("lastStage")
        @Order(30)
        Stage lastStage() {
            return new NamedStage("last");
        }

        @Bean("firstStage")
        @Order(-10)
        Stage firstStage() {
            return new NamedStage("first");
        }

        @Bean("middleStage")
        @Order(10)
        Stage middleStage() {
            return new NamedStage("middle");
        }

        @Bean
        Pipeline pipeline(List<Stage> stages) {
            return new Pipeline(stages);
        }
    }

    private static void require(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        Events events;

        try (var context = new AnnotationConfigApplicationContext(
                DemoConfig.class)) {

            events = context.getBean(Events.class);
            Pipeline pipeline = context.getBean(Pipeline.class);

            List<String> order = pipeline.labels();
            List<String> init = events.snapshot();

            String[] dependsOn = context.getBeanFactory()
                    .getBeanDefinition("worker")
                    .getDependsOn();

            require(
                    order.equals(List.of("first", "middle", "last")),
                    "Collection @Order contract failed");

            require(
                    init.equals(List.of(
                            "init:bootstrap", "init:worker")),
                    "@DependsOn initialization contract failed");

            require(
                    Arrays.equals(
                            dependsOn, new String[] {"bootstrap"}),
                    "Missing depends-on bean definition metadata");

            System.out.println("pipeline=" + order);
            System.out.println("initialization=" + init);
            System.out.println("worker.dependsOn=" +
                    Arrays.toString(dependsOn));
        }

        List<String> afterClose = events.snapshot();
        require(
                afterClose.equals(List.of(
                        "init:bootstrap", "init:worker",
                        "destroy:worker", "destroy:bootstrap")),
                "@DependsOn destruction contract failed");

        System.out.println("shutdown=" + afterClose);
    }
}
```

### 9.3. Run Command

From the project directory:

```bash
gradle run --quiet
```

If using the Gradle Wrapper:

```bash
./gradlew run --quiet
```

Windows PowerShell:

```powershell
.\gradlew.bat run --quiet
```

Stdout **deliberately printed by the program**:

```text
pipeline=[first, middle, last]
initialization=[init:bootstrap, init:worker]
worker.dependsOn=[bootstrap]
shutdown=[init:bootstrap, init:worker, destroy:worker, destroy:bootstrap]
```

Gradle or the Spring logging backend may emit extra lines outside `System.out.println`. The assertions cause the program to fail if observed behavior violates the declared contracts.

### 9.4. Line-by-Line Analysis

**`pipeline=[first, middle, last]`:** The three target bean definitions have order metadata `-10`, `10`, and `30`. When the BeanFactory resolves the `List<Stage> stages` parameter for `pipeline`, it sorts the candidates. `Pipeline` simply stores that `List` and prints labels in order.

**`initialization=[init:bootstrap, init:worker]`:** Bean `worker` carries `@DependsOn("bootstrap")`. Even though `worker()` is declared before `bootstrap()` in Java source, the BeanFactory must ensure `bootstrap` is already initialized before `worker` when `worker` is created. The stage beans do not append events to the log, so the snapshot contains only two init events with deterministic values.

**`worker.dependsOn=[bootstrap]`:** Metadata stored in `BeanDefinition`. This is an exact way to verify that the annotation on the factory method created the dependency relationship you intended.

**`shutdown=[init:bootstrap, init:worker, destroy:worker, destroy:bootstrap]`:** When the context closes, singleton dependent `worker` is destroyed before `bootstrap`. Both classes implement `AutoCloseable`; `@Bean(destroyMethod="close")` is declared explicitly to avoid relying on inferred destruction callbacks.

### 9.5. Why Is Declaring Methods in Reverse Order Important?

`worker()` is written before `bootstrap()` intentionally. This prevents readers from confusing source order with a business rule. The program does not **rely on** source order; it relies on `@DependsOn`. If configuration is later split across multiple files or method order changes, the dependency relation still expresses the same requirement.

### 9.6. Why Not Use Stage Constructor Order as Proof of `@Order`?

`@Order` only asserts order when the **`List` is resolved**; it does not require `Stage` constructors/factory methods to be invoked in that order. To avoid drawing a false conclusion, the demo checks **`pipeline.labels()`** without recording creation events for `Stage`. Conversely, the demo records creation/destruction events for `@DependsOn` because that is that annotation's actual contract.

### 9.7. Why Does `Events` Not Have `@Order`?

`Events` is just a collector. It is not injected into `List<Stage>` and is not a stage. Order metadata on it would not alter `bootstrap`/`worker` initialization. It is created by the BeanFactory to record events, not to impose an ordering policy itself.

### 9.8. Could Constructor Injection Replace It?

If `Worker` genuinely needed the `Bootstrap` object, use:

```java
@Bean("worker")
Worker worker(Bootstrap bootstrap, Events events) {
    return new Worker(events);
}
```

Then `Bootstrap` is resolved before calling `worker(...)` due to the factory method parameter. `@DependsOn` becomes unnecessary if only that object dependency is needed; however, the demo deliberately avoids injecting `Bootstrap` to illustrate an ordering dependency not expressed via direct object reference.

This is an **illustrative alternative snippet**, not the complete demo, and does not preserve independent destruction-order metadata across every setup if you remove the explicit relationship; test lifecycles when changing how dependencies are expressed.

## 10. Negative Test Scenarios: Wrong Usages

### 10.1. Using `@Order` to Force Init-Before

Wrong for the goal:

```java
@Bean
@Order(-100)
Bootstrap bootstrap() { return new Bootstrap(); }

@Bean
@Order(100)
Worker worker() { return new Worker(); }
```

These snippets assume no-arg constructors. There is **no dependency edge** between the two definitions. If `Worker` requires `Bootstrap` to initialize first, use `@DependsOn` or real DI instead of relying on order values.

### 10.2. Using `@DependsOn` to Sort a Pipeline

```java
@Bean
@DependsOn("authenticationStage")
Stage auditStage() { return new AuditStage(); }
```

This declaration can make `authenticationStage` initialize before `auditStage`, yet does not automatically sort `List<Stage>` as "authentication then audit" when the collection is injected. You need `@Order`/`Ordered` or a consumer sorting contract.

### 10.3. Putting `@Order` on a Configuration Class for Bean Methods

```java
@Configuration
@Order(-100)
class MyConfig {
    @Bean Stage x() { return new StageX(); }
    @Bean Stage y() { return new StageY(); }
}
```

`@Order(-100)` on `MyConfig` is configuration-level metadata; it does not become order `-100` for both `x` and `y`. To put `x` before `y` in an injected `List`, annotate each `@Bean` method or target class.

### 10.4. Relying on XML/Java Source Order

`worker` written below `bootstrap` today does not imply `Worker` always initializes after `Bootstrap` under every composition and startup mode. An import/scan refactoring can change how definitions are registered. Use explicit dependencies.

### 10.5. A Misspelled Dependency Name

```java
@Bean
@DependsOn("bootstarp")
Worker worker() {
    return new Worker();
}
```

The name `bootstarp` has a typo. The BeanFactory can throw `NoSuchBeanDefinitionException`/`BeanCreationException` when creating `worker` because the named dependency does not exist. `@DependsOn` does not fuzzy-match similar bean names. Write integration tests checking context refresh and metadata when renaming.

### 10.6. Dependency Cycle

If A has `@DependsOn("B")` and B has `@DependsOn("A")`, the BeanFactory encounters a dependency cycle and bean creation can fail. Do not use `@Order` to "solve" a cycle: a list-sorting annotation does not repair the dependency graph.

### 10.7. `@Lazy` and `@DependsOn`

A lazy bean `Worker` has `@DependsOn("bootstrap")`. It is not created at refresh if no consumer pulls it in. When `Worker` is actually requested, the container must initialize `Bootstrap` before `Worker`. `@DependsOn` does not automatically mean "every named dependency must be created right at refresh" if the dependent itself is not instantiated yet.

### 10.8. Prototype and Shutdown

`@DependsOn` can govern prototype initialization when the BeanFactory creates the prototype, yet **Spring does not automatically invoke destroy callbacks for all prototype instances on context close** like it does for singletons. Therefore do not infer singleton-like destruction-order guarantees when the dependent side is a prototype.

## 11. Scope of `@Order` Across Other Framework Components

Ordering appears in many places in Spring, yet you must identify **which unit is actually being sorted**:

- Autowired `List<Handler>` or `Handler[]`: BeanFactory sorts candidates by `Ordered`/`@Order`.
- `ObjectProvider<T>.orderedStream()`: stream API with ordering semantics based on the appropriate comparator.
- BeanPostProcessors/BeanFactoryPostProcessors have specific ordering/registration rules; do not assume every extension point only needs `@Order` on a class.
- MVC interceptors, security filters, AOP advisors: may have their own ordering APIs; an annotation placed on the wrong type does not override those infrastructure rules.
- `@Configuration` classes: `@Order` affects evaluation order within the set of configuration classes; it does not control product bean startup using the same number.

### 11.1. `ObjectProvider.orderedStream()`

In Spring, `ObjectProvider<T>` can retrieve candidates of type `T` as an ordered stream, for example:

```java
List<Step> ordered = provider.orderedStream().toList();
```

Requires a valid `ObjectProvider<Step> provider`. `orderedStream()` is useful when you want to **defer obtaining a set of plugins until usage time** while still applying order metadata. Do not equate stream order with startup init order.

### 11.2. `SmartLifecycle` When Start/Stop Ordering Is Needed

If your problem is **background services starting/stopping in phases** (schedulers, broker consumers, servers, network listeners), you may need:

```java
public final class WorkerLifecycle implements SmartLifecycle {
    @Override
    public int getPhase() {
        return 100;
    }

    // Methods isRunning, start, stop,
    // isAutoStartup, stop(Runnable) must be fully implemented.
}
```

This is a **non-standalone excerpt** intended to illustrate phases. Spring's `SmartLifecycle` starts lower-numbered phases first and stops in reverse order. Distinguish:
- **Bean creation/init** normally occurs before the lifecycle start loop;
- **`SmartLifecycle.start/stop`** has its own phase/order rules;
- `@DependsOn` can also influence startup/shutdown dependency relationships;
- pipeline `@Order` is not a start/stop phase.

When real infrastructure startup order is needed, examine `SmartLifecycle.getPhase()` as well instead of trying to force everything with `@Order` or reordering `@Bean` source methods.

### 11.3. Does the `@Priority` Annotation Differ from `@Order`?

Spring supports `jakarta.annotation.Priority` for many ordering scenarios (requiring the matching Jakarta annotation API on the classpath). `@Priority` also carries semantics in certain situations where Spring must pick **one** element among multiple candidates; `@Order` does not carry the same guarantee for single-bean selection. `@Priority` cannot be placed on a `@Bean` method if that annotation's Java `@Target` does not allow methods. When individual `@Bean` definitions need collection ordering, use `@Order` on the method.

## 12. Practical Testing: Which Assertions to Write?

A good test suite separates contracts instead of printing one event sequence and guessing.

### 12.1. Test List Order

```java
List<String> names = pipeline.labels();
if (!names.equals(List.of("first", "middle", "last"))) {
    throw new AssertionError("Wrong pipeline order");
}
```

This is a fragment based on the Section 9 demo. It verifies **order at the injection point**; it does not verify init order.

### 12.2. Test depends-on Metadata

```java
String[] requires = context.getBeanFactory()
        .getBeanDefinition("worker").getDependsOn();

if (!Arrays.equals(
        requires, new String[] {"bootstrap"})) {
    throw new AssertionError("Missing depends-on");
}
```

This fragment inspects container metadata. It proves the right bean-name dependency was registered, though it does not substitute for a lifecycle integration test if behavior is complex.

### 12.3. Test Init-Before

Create two beans with callbacks/constructors recording into `Events`. Verify `bootstrap` precedes `worker`. Avoid putting many unrelated constructors into the log and expecting all events to follow an unnecessary total order.

### 12.4. Test Shutdown

Close the context with try-with-resources or explicit `close()`; verify dependent destroy runs before dependency destroy. If beans implement `SmartLifecycle` or have async shutdown, verify the corresponding phase/callback contract separately.

### 12.5. Test When Reordering Declarations

Move factory methods to another config class, or reverse method source order in a test fixture. If contracts are properly expressed via `@Order` and `@DependsOn`, list order and the init-before relationship must still hold. This is an excellent test against accidental reliance on source order.

### 12.6. Test Missing Bean

Intentionally change `@DependsOn("bootstrap")` to `@DependsOn("missingBootstrap")` in a **separate test configuration**, expecting startup or lookup of the dependent bean to fail. Inspect the exception root cause; avoid catching every `Exception` and treating any error as proof of dependency checking.

### 12.7. Test Multiple Beans with the Same Order Value

If two stages share `@Order(10)`, build a test checking **whether business logic requires tie-breaking**. If a deterministic total order across refactorings is required, assign distinct order values or sort by an explicit application key. Do not assert an arbitrary tie order unless it is an actual requirement.

## 13. Troubleshooting Table

| Symptom | Explanation | How to handle |
| --- | --- | --- |
| Stage has `@Order(-100)` yet is created after another Stage | `@Order` does not control startup | Use dependency graph/`@DependsOn` if init-before is needed |
| List order is wrong when `@Order` is put on config class | Configuration-level order does not propagate to `@Bean` methods | Annotate target classes or individual `@Bean` methods |
| `@DependsOn` is present yet List still has wrong order | `@DependsOn` does not sort collections | Use `@Order`/`Ordered` |
| Changing XML bean order changes init order | Relying purely on registration side effects | Declare explicit dependencies |
| `NoSuchBeanDefinitionException` with `@DependsOn` | Wrong bean name or unregistered bean | Check names/aliases/profiles |
| Circular depends-on | Explicit A↔B dependencies | Refactor graph, remove cycle |
| `@Primary` attached yet List still holds multiple beans | Primary only picks a single injection candidate | Use `@Order` for lists, or qualifiers to filter |
| `@Order` does not automatically pick one implementation | Single-bean resolution differs from collection sorting | `@Qualifier`/`@Primary` |
| Handler injected in right List yet business calls differ in order | Consumer ignores collection order | Iterate the List per contract |
| Lazy bean with `@DependsOn` not created at startup | Dependent has not been instantiated yet | Check what triggers dependent creation |
| Prototype bean does not destroy in shutdown order | Prototype lifecycle differs from singleton | Clean up instances in owner/application |
| Bean has `@DependsOn` on class yet XML ignores it | XML registration skips class-level annotation in cases noted by Javadoc | Use XML `depends-on` |
| `SmartLifecycle` start order wrong | Confusing startup phases with bean init | Use `getPhase()`/dependencies and test |
| Unordered List changes order when adding package scan | Registration order/candidate set changed | Set explicit `@Order` |
| `Ordered` interface has no effect | Consumer does not use comparator/ordered injection | Identify where ordering applies |
| XML `<import>` order changes nothing to fix error | File order is not a dependency contract | Design init dependencies properly |
| BeanPostProcessor runs in different order | Processor infrastructure has its own rules | Check `PriorityOrdered`/`Ordered` and registration semantics |
| Trying to force all beans into a single total sequence | Actual order is a partial dependency graph | Declare only necessary dependencies |

### 13.1. Evidence-First Debugging Steps

1. **Read the real question:** do you need List order, init callback order, start/stop order, or display order?
2. **Check bean candidates:** which bean names/types/qualifiers actually exist in the context?
3. **For Lists:** inspect annotations on **target beans/`@Bean` methods** and `Ordered` implementations; check order values.
4. **For startup:** inspect constructor injection, `@DependsOn` metadata, `@Lazy`, and infrastructure beans.
5. **For shutdown:** close the context properly; inspect destroy callbacks and dependency direction.
6. **For source order:** record registration order if needed for debugging, yet never turn that trace into an API guarantee.
7. **For lifecycle services:** distinguish bean initialization from `SmartLifecycle.start()`/`stop()` phases.
8. **Read the root cause:** missing dependency/circular reference errors differ completely from ambiguous collections or wrong sorting.
9. **Test on the actual Spring version:** Spring 6.2 has background initialization and candidate-selection rules that can affect old assumptions.
10. **Do not fix by "swapping two methods"** before checking whether a dependency contract is missing.

## 14. Exercises with Answers

### Exercise 1 — Choosing the Annotation

A system has three `Handler`s and wants handlers in an injected `List<Handler>` ordered authenticate → validate → audit. What should be used?

**Answer:** `@Order` or `Ordered` on the handler beans (or explicit sorting) with the consumer iterating the ordered List. Do not use `@DependsOn` merely to sort a List.

### Exercise 2 — Side Effect Must Be Ready First

Bean `worker` needs a `schemaMigrator` to run initialization before `worker` initializes, without holding a reference to the migrator. What should be used?

**Answer:** `@DependsOn("schemaMigrator")` on `worker`, or establish a real dependency if there is an object relationship in the domain.

### Exercise 3 — Two Beans Written in Order in Java

Method `@Bean Service a()` sits before `@Bean Service b()`. Does that automatically guarantee `a` is created before `b`?

**Answer:** No such dependency contract exists. Bean creation is governed by the BeanFactory graph, scopes, and startup processing.

### Exercise 4 — Negative or Positive?

`@Order(-5)` and `@Order(15)` on two `Step`s. Which comes first in an ordered List?

**Answer:** `-5` comes first because smaller numbers have higher precedence.

### Exercise 5 — `@Order` on Configuration

`@Configuration @Order(-100)` has two `@Bean Step` methods with no order metadata. Do both automatically inherit `@Order(-100)`?

**Answer:** No. Configuration-level `@Order` affects evaluation order of configuration classes, and does not automatically apply to product beans.

### Exercise 6 — Registration Fallback

No `Stage` has `@Order`. What do the Spring docs say `List` order normally falls back to?

**Answer:** Registration order of target bean definitions. However, do not rely on source declaration order as a long-term guarantee.

### Exercise 7 — Destroy Sequence

`@DependsOn("bootstrap")` is placed on bean `worker`, and both singletons have destroy callbacks. Which is destroyed first?

**Answer:** `Worker` is destroyed before `Bootstrap` on context shutdown per the dependency relation.

### Exercise 8 — `@Order` and Singleton Startup

`@Order(0)` on `FastHandler`, `@Order(100)` on `SlowHandler`. Does that force `FastHandler`'s constructor to always run before `SlowHandler`?

**Answer:** No. `@Order` does not govern singleton initialization order.

### Exercise 9 — Bean Name

Bean is declared `@Bean("primaryCache")`, consumer has `@DependsOn("Cache")`. Does Spring automatically match by class type?

**Answer:** No. `DependsOn` uses names/aliases, so use `"primaryCache"` or a valid alias name.

### Exercise 10 — Constructor Injection Instead of Ordering

Bean B has constructor `B(A a)` and A is a Spring bean. Do you need `@DependsOn("a")` just to ensure A is resolved before B is constructed?

**Answer:** Usually no; constructor injection is a real dependency edge that already forces Spring to resolve A. `@DependsOn` is useful for other side effects without parameters.

### Exercise 11 — `@Primary`

There are three `Stage` beans, one marked `@Primary`. When injecting `List<Stage>`, does Spring inject only the primary bean?

**Answer:** No. Collection injection normally receives all eligible beans; separate ordering/filtering determines the set and order.

### Exercise 12 — `@Qualifier`

A consumer needs a `List<Stage>` containing only the `critical` group, sorted. Which steps are needed?

**Answer:** Filter using appropriate qualifier/selection metadata, then apply ordering within the candidate set via `@Order`/`Ordered` or explicit sorting.

### Exercise 13 — `@DependsOn` Cycle

Bean A `dependsOn` B, B `dependsOn` A. Can this be resolved with `@Order(0)` and `@Order(1)`?

**Answer:** No. A cyclic dependency graph must be redesigned; `@Order` does not remove dependency edges.

### Exercise 14 — Prototype and Destruction

Prototype `Worker` `dependsOn` Singleton `Bootstrap`. When the context closes, does Spring automatically track down all issued prototype `Worker`s and run destroy before `bootstrap`?

**Answer:** No. Spring does not automatically manage destruction for all prototypes like singletons; the owner must handle cleanup properly.

### Exercise 15 — SmartLifecycle

A server needs Listener A to start before Listener B and stop after B; both beans implement `SmartLifecycle`. Which mechanism should be used?

**Answer:** `getPhase()` and corresponding dependencies; lower phases start first and stop last, rather than using List `@Order` to force lifecycle ordering.

### Exercise 16 — Equal Orders

Two beans have `@Order(10)`, and absolute order between them matters greatly. Should you rely on scan/registration order?

**Answer:** No; assign distinct order values or use an explicit application comparator/key and test it.

### Exercise 17 — Testing Scope

In the demo, `Pipeline` prints the right order while `Events` shows the reverse init order. Can both be valid under the Spring contract?

**Answer:** Yes. Collection sorting and singleton initialization are two independent goals; check the dependency graph.

### Exercise 18 — Annotation on an XML-Declared Class

Class `Worker` carries `@DependsOn("bootstrap")`, yet is declared via `<bean class="...">` in legacy XML. Is the class-level annotation guaranteed to apply?

**Answer:** Per `@DependsOn` Javadoc, class-level annotations are processed via component scanning; when registered via XML as noted in the Javadoc, use XML `depends-on` to ensure it.

### Exercise 19 — Adding `@Order` to an Infrastructure Bean

A `BeanFactoryPostProcessor` runs too late; the team only adds `@Order(-999)` without checking how the processor is registered. Is that enough?

**Answer:** Not yet. Infrastructure extension points have their own ordering policies (`PriorityOrdered`/`Ordered` and registration rules); consult the exact extension point.

### Exercise 20 — Multiple Dependencies Requirement

`Service` must wait for `Migrator` and `CacheWarmup`, and `CacheWarmup` must wait for `Migrator`. Should you only put `@DependsOn({"migrator","cacheWarmup"})` on `service`?

**Answer:** That does not directly express the dependency between `CacheWarmup` and `Migrator`. Declare `cacheWarmup` `dependsOn` `migrator`, and `service` `dependsOn` `cacheWarmup` (plus any other genuinely needed relations).

## 15. Checklist Before Merging Bean Ordering Configuration

- Is the requirement **List order**, **bean init-before**, or **runtime start/stop**?
- For Lists, is `@Order` placed on **target beans/`@Bean` methods** rather than only the config class?
- Is the smaller-number-comes-first convention respected? Are there ties affecting business logic?
- Does the consumer actually iterate the ordered List rather than looking up by name/map?
- Are `@Primary`/`@Qualifier` used properly to select/filter candidates rather than confused with ordering?
- If order metadata is absent, are you relying on registration fallback as a fragile contract?
- For init dependencies, does `@DependsOn`/constructor injection express the real dependency edge?
- Do names in `@DependsOn` actually exist per XML/JavaConfig/alias registration?
- Is class-level `@DependsOn` actually read by Spring under the current bean registration method?
- Do lazy/prototype/FactoryBean/background init alter dependency creation timing?
- For singleton destruction, have you tested dependent destruction before dependency on context close?
- Have you accidentally introduced a `dependsOn`/dependency graph cycle?
- For `SmartLifecycle`, have you used dedicated phase/start/stop semantics where needed?
- Do tests verify **both** the injected List and startup/shutdown logs rather than conflating them in one assertion?
- Would refactoring imports, scan roots, or source file method order break any real contract?
- Is ordering metadata documented in module docs so maintainers do not break it accidentally?

## 16. Summary

**`@Order`** answers "when multiple candidates of the same type are consumed as a list, which element comes first?"; smaller numbers have priority. The annotation can be placed on bean classes or individual `@Bean` methods; when placed on a `@Configuration` class, it does not automatically propagate order to individual product beans. `@Order` **does not** guarantee singleton creation order.

**`@DependsOn`** answers "to create this bean, which beans must be initialized first?" and, for singleton beans, "at shutdown, which dependency must the dependent be destroyed before?". It uses **bean names**, not Java class names, and does not sort Lists.

**Definition/registration order** is a separate axis: Spring may use registration order as a fallback for unordered injected Lists, yet source method/XML order **is not** a standard way to enforce init-before. Choose the right abstraction for the requirement: `@Order` for collections needing sorting; DI or `@DependsOn` for initialization dependencies; `SmartLifecycle` phases for start/stop services.

### Official Spring Framework 6.2 Documentation

- [Spring Framework 6.2 — Using `@Autowired`, section Arrays and Collections](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired.html).
- [Spring Framework 6.2 — Using `depends-on`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-dependson.html).
- [Spring Framework 6.2 — Composing Java-based Configurations, startup singletons](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html).
- [Spring Framework 6.2 — `@Order` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/annotation/Order.html).
- [Spring Framework 6.2 — `@DependsOn` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/DependsOn.html).
- [Spring Framework 6.2 — Customizing the Nature of a Bean: Lifecycle and `SmartLifecycle`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html).
- [Spring Framework 6.2 — `@Bean` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/Bean.html).
