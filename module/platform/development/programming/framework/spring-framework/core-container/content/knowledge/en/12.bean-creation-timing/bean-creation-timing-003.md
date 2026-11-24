# Lazy Beans Can Still Be Created by Non-Lazy Dependencies in Spring Core Container

## 1. What Problem Does This Lesson Solve?

A bean marked `@Lazy` does not necessarily "survive" startup without an instance. In Spring Framework, **a non-lazy singleton (*eager singleton*) can pull a lazy bean declared as its dependency into early initialization**. This is a core rule of the **Bean Creation Timing** topic in Spring Core Container.

Example:

```java
@Configuration(proxyBeanMethods = false)
class ApplicationConfig {
    @Bean
    @Lazy
    PricingRules pricingRules() {
        return new PricingRules();
    }

    @Bean
    CheckoutService checkoutService(PricingRules pricingRules) {
        return new CheckoutService(pricingRules);
    }
}
```

This is an **illustrative sample**, assuming `PricingRules` and `CheckoutService` have valid constructors. There are two bean definitions:

- `pricingRules`: lazy singleton because the `@Bean` method has `@Lazy`.
- `checkoutService`: **non-lazy** singleton because it does not have `@Lazy`.

When `ApplicationContext.refresh()` performs pre-instantiation, Spring must create `checkoutService`. However, to call the factory method `checkoutService(PricingRules pricingRules)`, the container **must supply a `PricingRules` object**. Therefore `pricingRules` is created right at startup, despite its own bean definition carrying `@Lazy`.

This is not a bug in Spring. It reflects the **dependency contract**: lazy initialization has lower priority than the need to successfully construct an eager bean that depends on it.

### Learning Objectives

After this lesson, you will:

1. Correctly explain `singleton`, `eager`, `lazy`, and `dependency-driven instantiation`.
2. Distinguish **lazy on a bean definition** from **lazy at an injection point**.
3. Know why a constructor/factory method parameter of an eager bean causes a lazy dependency to be created.
4. Trace an A→B→C chain when eager A pulls in multiple lazy beans.
5. Predict when constructors, init callbacks, and post-processors execute.
6. Understand `@Lazy` on `@Bean`, `@Component`, `@Configuration`, and XML `lazy-init`.
7. Use `@Lazy` at an injection point to receive a lazy-resolution proxy **when appropriate**.
8. Use `ObjectProvider<T>` to perform lookup when genuinely needed.
9. Avoid misunderstanding `@DependsOn`, `prototype`, and `FactoryBean`.
10. Inspect `BeanFactory.containsSingleton(...)` to check state without accidentally creating the bean.
11. Run a standalone Java 17/Spring Framework example with deterministic output demonstrating every branch.
12. Apply sensible startup, latency, reliability, and testing design in projects.

**Rule to remember:** Marking a bean `@Lazy` only states that Spring **does not proactively pre-instantiate it as a regular eager singleton**. If an eager bean **requires the real instance of that bean**, Spring will create it to fulfill the dependency.

## 2. Reading Scope, Lazy Flag, and Dependency Edges Together

Three attributes must be examined **together** when predicting when a bean is created:

| Axis | Question | Example |
| --- | --- | --- |
| Scope | Does the container reuse or create a new instance? | `singleton` normally reuses the same bean instance within a container; `prototype` creates per lookup |
| Definition lazy flag | Is the bean proactively pre-instantiated? | `@Lazy` skips the proactive non-lazy singleton pass |
| Dependency edge | Which bean must obtain an instance of another bean? | Eager A directly receiving lazy B must still resolve B when creating A |

```text
A (singleton, eager)
    └── constructor requires B (singleton, @Lazy)
                              └── B is created when A initializes
```

With `AnnotationConfigApplicationContext`, a regular non-lazy singleton is normally created by the time `refresh()` completes. However, **B having a lazy flag does not mean every caller must wait until after startup**; it is still created if an eager consumer demands the real target. Conversely, if A receives a proxy via `@Lazy` at the injection point or holds an `ObjectProvider<B>` without looking it up yet, that edge alone does not need B right away.

Do not confuse a registered `BeanDefinition` with a created instance. To observe a lazy singleton before first use, check `containsSingleton("beanName")` instead of `getBean()`, because `getBean()` is the very operation that can cause B to be created. Scope and pre-instantiation concepts were covered in the opening lesson; this lesson traces **dependency edges causing early creation**.

## 3. When Does Spring Pre-Instantiate Singletons?

In Spring Framework, `ApplicationContext.refresh()` includes a phase creating non-lazy singleton beans via the BeanFactory and the corresponding `preInstantiateSingletons()` mechanism.

Simplified model:

```text
Read @Configuration / XML / component scan
                  |
                  v
       Register BeanDefinitions
                  |
                  v
  BeanFactoryPostProcessor, BeanPostProcessor
                  |
                  v
   preInstantiateSingletons() during refresh
                  |
        Iterate non-lazy singletons
                  |
           Create eager bean A
                  |
           Resolve dependencies
                  |
          Is lazy B required?
             /          \
           Yes           No
            |             |
       Create B early   B remains deferred
            |
        Complete A
                  |
                  v
           Refresh complete
```

Some infrastructure beans have special lifecycles and are created before this phase; the diagram only illustrates **regular beans** logic.

### "Lazy Bean" Means Skipping the Pre-Instantiation Pass, Not Rejecting Every Creation Request

Spring does not enforce a ban "B must not be created before the first request" for `@Lazy` beans. The container only has a **lazy-init flag** affecting the proactive initialization path. Real requests from `getBean`, dependency injection, another bean's lookup, and certain extension points can still cause that bean to be created.

### Pre-Instantiation Does Not Mean Creating Every Bean on the Classpath

Only classes with matching bean definitions are managed by the container. Prototypes and other scopes are not bulk pre-instantiated like regular non-lazy singletons. However, they **can be created on demand when acting as dependencies of eager singletons**.

### Why Does Spring Do This?

If Spring skipped a required dependency merely because the bean was marked lazy, bean A would lack a constructor parameter, producing an invalid object or failing creation. Spring prioritizes ensuring an eager bean is completed according to its dependency contract.

## 4. Eager A, Lazy B Example: The Actual Result

Given two POJOs:

```java
public final class ExchangeRateTable {
    public ExchangeRateTable() {
        System.out.println("ExchangeRateTable constructed");
    }
}

public final class InvoiceService {
    private final ExchangeRateTable rates;

    public InvoiceService(ExchangeRateTable rates) {
        this.rates = rates;
        System.out.println("InvoiceService constructed");
    }
}
```

This is an **illustrative** example; two public top-level classes must be placed in separate `.java` files if copied, and do not form a complete standalone program.

Configuration:

```java
@Configuration(proxyBeanMethods = false)
class Config {
    @Bean
    @Lazy
    ExchangeRateTable exchangeRateTable() {
        return new ExchangeRateTable();
    }

    @Bean
    InvoiceService invoiceService(ExchangeRateTable table) {
        return new InvoiceService(table);
    }
}
```

When the context is created and refreshed:

```java
try (var context = new AnnotationConfigApplicationContext(Config.class)) {
    System.out.println("Context ready");
}
```

Lines from **both bean constructors** can appear before `Context ready`; the required logical order is **ExchangeRateTable must be created before the InvoiceService constructor receives it**. Other independent beans or logging may interleave, so the runnable example in Section 10 will not rely on global log order.

Takeaway: Adding `@Lazy` to `exchangeRateTable` without changing how `invoiceService` depends on it **does not defer the rate table's construction cost**.

## 5. Dependency Chains: An Eager Bean Can Pull In Many Lazy Beans

It is not just A→B. One eager bean can pull in an entire graph:

```text
WebFacade            eager
    |
    v
CheckoutService      lazy
    |
    v
PriceCalculator      lazy
    |
    +---> TaxTable    lazy
    |
    +---> ExchangeRates lazy
```

If `WebFacade`'s constructor requires `CheckoutService`, the service constructor requires the calculator, and the calculator requires tax table and rates, Spring must resolve the whole chain to build the facade. It does not matter which Java files or configuration modules the `@Bean`s reside in.

Two consequences follow from this:

- **Marking every lower-layer bean `@Lazy` does not guarantee faster startup** if a root eager bean still requires the whole graph.
- To genuinely defer, you must change the **dependency edge**, such as making an injection point a lazy proxy or having the consumer bean hold a provider to fetch the collaborator at usage time.

### This Graph Differs from the Import Graph

`@Import(ServiceConfig.class)` merely brings another configuration into the same context. It does not mean the BeanFactory must immediately create every lazy singleton declared in the imported config. Conversely, as soon as one eager bean anywhere in the context needs a lazy bean from that module, it can still be initialized.

### Do Not Rely on @Bean Method Order

When `@Bean a()` appears before `@Bean b()` in source code, that is not a way to specify "a is created before b" in business semantics. Spring resolves dependencies and lifecycles. To predict whether a lazy bean has been created, look at the **dependency graph**, not method order.

## 6. @Lazy on Bean Definition vs @Lazy at Injection Point Differ

This is the most important distinction after the rule at the beginning of the lesson.

### 6.1. @Lazy on a Bean Definition

```java
@Bean
@Lazy
RulesEngine rulesEngine() {
    return new RulesEngine();
}
```

This means the `rulesEngine` bean is not selected for default eager pre-instantiation. However, if an eager service needs `RulesEngine` as a normal constructor parameter, Spring still creates the instance and injects it.

### 6.2. @Lazy at an Injection Point

```java
@Bean
BillingService billingService(@Lazy RulesEngine rulesEngine) {
    return new BillingService(rulesEngine);
}
```

Spring supports `@Lazy` at an injection point: given suitable dependency/proxying conditions, it can pass a **lazy-resolution proxy** instead of creating the target `RulesEngine` immediately. Only when code actually invokes a method on the proxy does Spring resolve the target bean.

This differs from `@Lazy` on the bean factory method itself. The two annotations adjust two different aspects:

| Where placed | What it adjusts | Typical outcome |
| --- | --- | --- |
| `@Lazy` on `@Bean rulesEngine()` | `rulesEngine` definition is lazy | Skips proactive pre-instantiation pass, yet still created if an eager consumer needs it directly |
| `@Lazy` on parameter `billingService(@Lazy RulesEngine r)` | How the dependency is resolved at the injection point | Consumer can receive a proxy; target is resolved when proxy is used |
| Both | Lazy definition + lazy injection point | Target has a chance to remain uncreated when the eager consumer is built |
| Only `@Lazy` on consumer `@Bean billingService()` | The consumer itself is deferred | Consumer is not directly pre-instantiated if no other eager dependency needs it |

### 6.3. A Proxy Is a Real Object, Yet the Target May Not Exist Yet

When Spring injects a proxy, the consumer constructor **has already received a Java reference**. However, that reference can be a proxy responsible for **resolving the target when called**, rather than an initialized target instance. Thus you must distinguish:

- **Proxy is created** to be injected into the eager bean.
- **Target bean is created** when the proxy is dereferenced/invoked.
- **Eager consumer bean is created** during refresh.

If code invokes a method on the proxy right inside the consumer's constructor or `@PostConstruct`, Spring may still have to initialize the target during startup. Annotations have no "magic" guaranteeing the target stays deferred regardless of what the consumer does.

### 6.4. Proxies Do Not Apply Arbitrarily to Every Type

An interface is a favorable target dependency for JDK dynamic proxies. For concrete classes, Spring may require a class-based proxy subject to bytecode/type suitability. `final` types or `final` methods and unproxiable cases have significant limitations. The runnable sample will use the **`RemoteGateway` interface** for the deferred proxy.

### 6.5. @Lazy at an Injection Point Does Not Turn a Required Dependency Optional

A lazy-resolution proxy can be injected without needing the target right away. If the target bean does not exist or resolution fails, the error may only appear when the proxy is used. Therefore **do not use `@Lazy` to mask a missing dependency**. If the collaborator is genuinely optional, use `ObjectProvider`/`Optional` under an explicit contract.

## 7. ObjectProvider<T>: Deferring Lookup with Explicit Code

Spring's `ObjectProvider<T>` lets a consumer hold a handle and request the target when needed:

```java
import org.springframework.beans.factory.ObjectProvider;

final class InvoiceExporter {
    private final ObjectProvider<RemoteGateway> gateways;

    InvoiceExporter(ObjectProvider<RemoteGateway> gateways) {
        this.gateways = gateways;
    }

    String export(String payload) {
        return gateways.getObject().send(payload);
    }
}
```

The code is an illustrative snippet requiring a `RemoteGateway` interface and corresponding bean definition. With a provider, the constructor does not have to fetch the target instance; the provider does its work when `getObject()` is called.

### Advantages Over a Hidden Proxy

- Code clearly states **when** lookup occurs.
- Can use `getIfAvailable()`/`getIfUnique()` when the dependency is genuinely optional.
- Easy to control per-lookup scoping with prototype/other scopes.
- No need to pretend the consumer holds "the exact target reference right at construction".

### Limitations

- If `getObject()` is called in an eager bean's constructor or init callback, the target is still created early.
- Using providers everywhere can obscure the dependency graph, creating a service-locator style that is harder to test.
- `getIfAvailable()` is not a proper way to silently ignore a mandatory collaborator.
- If multiple beans share the same type, `getObject()` can still encounter ambiguity; qualifiers or appropriate resolution configuration are needed.
- A provider only defers lookup; if the target object is slow to construct, first-use latency still exists.

### When to Choose @Lazy Injection Point vs Provider?

| Need | Consider |
| --- | --- |
| Want an interface collaborator to "look like a normal bean", resolved on method call | `@Lazy` injection point |
| Need to explicitly invoke lookup in a specific method | `ObjectProvider<T>` |
| Need a fresh prototype for each job | `ObjectProvider<T>` is usually clearer |
| Constructor needs the target immediately to establish invariants | Inject the bean directly, accept early creation |
| Truly optional dependency | Provider/Optional with explicit default behavior |
| Want to dodge a constructor cycle without changing design | Prefer neither; refactor the graph first |

## 8. @Lazy on @Component and @Configuration

### @Lazy on a Component Class

```java
@Component
@Lazy
public class OptionalAdapter {
    // ...
}
```

If component scanning registers this bean and no eager bean requires it, Spring normally does not create it during refresh. However, an eager singleton constructor-injecting `OptionalAdapter` will cause the adapter to be initialized just like the `@Bean` case.

### @Lazy on a @Configuration Class

```java
@Configuration
@Lazy
class FeatureConfig {
    @Bean
    FeatureCatalog featureCatalog() {
        return new FeatureCatalog();
    }
}
```

`@Lazy` placed on a configuration class can set default lazy-init for `@Bean` definitions of that configuration per the annotation contract. However:

- Another bean can still require `featureCatalog` and cause it to initialize early.
- `@Configuration` infrastructure/processing has its own rules; do not assume the configuration instance and every helper are strictly lazy.
- If a `@Bean` has an explicit `@Lazy(false)`, it can override default laziness.
- Always test in a real context per application version/scope.

### Do Not Confuse with @Primary or @DependsOn

`@Primary` resolves injection candidate priority. `@DependsOn` adds bean creation ordering constraints. Neither of those two annotations creates a lazy-resolution proxy for an injection point.

## 9. XML: lazy-init="true" Follows the Same Rules

Spring XML:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="priceRules"
          class="example.PriceRules"
          lazy-init="true"/>

    <bean id="checkoutService"
          class="example.CheckoutService">
        <constructor-arg ref="priceRules"/>
    </bean>
</beans>
```

If `CheckoutService` has a constructor requiring `PriceRules`, eager singleton `checkoutService` causes `priceRules` to be created at startup even though `priceRules`'s XML has `lazy-init="true"`.

### XML default-lazy-init

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       default-lazy-init="true">
    <bean id="a" class="example.A"/>
    <bean id="b" class="example.B"/>
</beans>
```

This is a shortened syntax snippet; a full schema is needed in a real file. `default-lazy-init="true"` can change the default for definitions in that scope; an explicit `lazy-init="false"` can still be declared for a bean. If another eager bean requires A, A is still created.

### @ImportResource Does Not Change Lazy Semantics

Whether XML is read via `ClassPathXmlApplicationContext` or imported through Java:

```java
@Configuration
@ImportResource("classpath:legacy.xml")
class RootConfig {
}
```

bean definitions once registered still share the same BeanFactory, scopes, and dependency rules. Placing an XML resource in a separate module does not prevent a lazy bean from being injected by an eager Java `@Bean` consumer.

## 10. Runnable Java 17 Project: Three Different Observation Cases

The complete example below demonstrates within the same `ApplicationContext`:

- **`requiredIndex` is marked `@Lazy` yet is pulled into startup by `eagerCatalogService`.**
- **`idleReport` is lazy and not requested by any eager bean, so it remains uncreated after refresh.**
- **`remoteGateway` is lazy while eager `deferredConsumer` receives `@Lazy RemoteGateway` at the injection point**, so the consumer can be created without creating the target gateway yet; only when invoking a method through the proxy is it initialized.
- `containsSingleton(name)` observes the singleton cache without causing the lazy bean to be created.
- A lazy singleton preserves identity once created.
- Deterministic output that does not depend on constructor order of independent singletons.

### 10.1. Project Structure

```text
lazy-dependency-demo/
├── pom.xml
└── src/main/java/demo/
    └── LazyDependencyDemo.java
```

### 10.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>lazy-dependency-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

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
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 10.3. Complete LazyDependencyDemo.java File

```java
package demo;

import java.util.HashSet;
import java.util.Set;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;

public class LazyDependencyDemo {

    public static final class Tracker {
        private final Set<String> created = new HashSet<>();

        public void mark(String name) {
            created.add(name);
        }

        public boolean has(String name) {
            return created.contains(name);
        }
    }

    public static final class RequiredIndex {
        public RequiredIndex(Tracker tracker) {
            tracker.mark("requiredIndex");
        }

        public String lookup(String key) {
            return "INDEX:" + key;
        }
    }

    public static final class EagerCatalogService {
        private final RequiredIndex index;

        public EagerCatalogService(RequiredIndex index, Tracker tracker) {
            this.index = index;
            tracker.mark("eagerCatalogService");
        }

        public String catalog(String key) {
            return index.lookup(key);
        }
    }

    public static final class IdleReport {
        public IdleReport(Tracker tracker) {
            tracker.mark("idleReport");
        }
    }

    public interface RemoteGateway {
        String send(String request);
    }

    public static final class RemoteGatewayImpl implements RemoteGateway {
        public RemoteGatewayImpl(Tracker tracker) {
            tracker.mark("remoteGateway");
        }

        @Override
        public String send(String request) {
            return "REMOTE:" + request;
        }
    }

    public static final class DeferredConsumer {
        private final RemoteGateway gateway;

        public DeferredConsumer(RemoteGateway gateway, Tracker tracker) {
            this.gateway = gateway;
            tracker.mark("deferredConsumer");
        }

        public String useGateway(String request) {
            return gateway.send(request);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        @Bean
        public Tracker tracker() {
            return new Tracker();
        }

        @Bean
        @Lazy
        public RequiredIndex requiredIndex(Tracker tracker) {
            return new RequiredIndex(tracker);
        }

        @Bean
        public EagerCatalogService eagerCatalogService(
                RequiredIndex requiredIndex, Tracker tracker) {
            return new EagerCatalogService(requiredIndex, tracker);
        }

        @Bean
        @Lazy
        public IdleReport idleReport(Tracker tracker) {
            return new IdleReport(tracker);
        }

        @Bean
        @Lazy
        public RemoteGateway remoteGateway(Tracker tracker) {
            return new RemoteGatewayImpl(tracker);
        }

        @Bean
        public DeferredConsumer deferredConsumer(
                @Lazy RemoteGateway remoteGateway, Tracker tracker) {
            return new DeferredConsumer(remoteGateway, tracker);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            Tracker tracker = context.getBean(Tracker.class);

            System.out.println("required.createdAtRefresh=" +
                    tracker.has("requiredIndex"));
            System.out.println("eager.createdAtRefresh=" +
                    tracker.has("eagerCatalogService"));
            System.out.println("idle.createdAtRefresh=" +
                    tracker.has("idleReport"));
            System.out.println("gateway.createdAtRefresh=" +
                    tracker.has("remoteGateway"));
            System.out.println("consumer.createdAtRefresh=" +
                    tracker.has("deferredConsumer"));

            System.out.println("gateway.hasSingletonBefore=" +
                    context.getBeanFactory().containsSingleton("remoteGateway"));

            EagerCatalogService eager =
                    context.getBean(EagerCatalogService.class);
            System.out.println("catalog=" + eager.catalog("B-17"));

            DeferredConsumer consumer =
                    context.getBean(DeferredConsumer.class);
            System.out.println("deferredCall=" +
                    consumer.useGateway("ping"));

            System.out.println("gateway.createdAfterCall=" +
                    tracker.has("remoteGateway"));

            IdleReport first = context.getBean(IdleReport.class);
            IdleReport second = context.getBean(IdleReport.class);

            System.out.println("idle.createdAfterLookup=" +
                    tracker.has("idleReport"));
            System.out.println("idle.sameSingleton=" +
                    (first == second));
        }
    }
}
```

### 10.4. Run Command

Requires JDK 17+, Maven, and access to download the Spring dependency from the appropriate repository if not already cached locally:

```bash
mvn -q clean compile exec:java -Dexec.mainClass=demo.LazyDependencyDemo
```

### 10.5. Program Output

Excluding Maven/Spring logs that may appear alongside the lines produced by `System.out.println`:

```text
required.createdAtRefresh=true
eager.createdAtRefresh=true
idle.createdAtRefresh=false
gateway.createdAtRefresh=false
consumer.createdAtRefresh=true
gateway.hasSingletonBefore=false
catalog=INDEX:B-17
deferredCall=REMOTE:ping
gateway.createdAfterCall=true
idle.createdAfterLookup=true
idle.sameSingleton=true
```

### 10.6. Exact Analysis of Each Group of Lines

**`required.createdAtRefresh=true`:** Even though `requiredIndex` carries `@Lazy`, Spring must create it when pre-instantiating `eagerCatalogService`. This is the core point of the lesson.

**`eager.createdAtRefresh=true`:** `eagerCatalogService` is a non-lazy singleton so it is created during refresh. The constructor marks `Tracker`.

**`idle.createdAtRefresh=false`:** `idleReport` has `@Lazy` and no eager consumer requests it. Therefore its constructor has not run before `main` fetches it.

**`gateway.createdAtRefresh=false`:** `remoteGateway` is a lazy singleton. Eager `deferredConsumer` does not require the target immediately because its factory method parameter is `@Lazy RemoteGateway`; Spring can inject a lazy-resolution proxy. `RemoteGatewayImpl`'s constructor has not run yet.

**`consumer.createdAtRefresh=true`:** `deferredConsumer` is an eager singleton and can be created with a proxy reference while the remote gateway target remains deferred.

**`gateway.hasSingletonBefore=false`:** `containsSingleton("remoteGateway")` inspects the singleton cache without causing target creation. The proxy injected into `deferredConsumer` does not cause the `remoteGateway` target singleton to appear in the registry.

**`catalog=INDEX:B-17`:** The eager service already has the real `RequiredIndex` instance and uses it to return the string. No `getBean(RequiredIndex.class)` call is needed here.

**`deferredCall=REMOTE:ping`:** When `DeferredConsumer.useGateway("ping")` invokes `send` on the proxy, Spring resolves the `remoteGateway` target and creates `RemoteGatewayImpl` if the target does not yet exist. Then the method returns the string.

**`gateway.createdAfterCall=true`:** The implementation constructor recorded the marker on first use of the proxy.

**`idle.createdAfterLookup=true`:** The first and second `context.getBean(IdleReport.class)` calls cause the lazy bean to be created and returned from the singleton cache.

**`idle.sameSingleton=true`:** Lazy does not change scope. Two lookups in the same context return the same `IdleReport` instance.

### 10.7. Why Does This Example Avoid Flakiness?

- `Tracker` is created in the same context; markers are only read after refresh.
- Does not print constructor logs to infer order among independent eager beans.
- `Set` is used for membership checks, never iterated, and does not depend on iteration order.
- No network calls, DB, clocks, or background threads.
- `RemoteGateway` is an **interface**, so the lazy-resolution proxy can work without running into final concrete class limitations.
- `@Configuration(proxyBeanMethods=false)` is valid because all dependencies pass through `@Bean` parameters rather than direct calls to other `@Bean` methods.
- Beans are `public static` nested classes; no outer `LazyDependencyDemo` instance is required.
- Does not read `remoteGateway` via `getBean` before checking cache state.
- Only checks singleton identity after the lazy bean has actually been looked up.
- `try-with-resources` closes the context and triggers appropriate lifecycle cleanup.

## 11. Small Tweaks to See the Core Behavior

### Try 1 — Remove @Lazy on requiredIndex

```java
@Bean
RequiredIndex requiredIndex(Tracker tracker) {
    return new RequiredIndex(tracker);
}
```

Output `required.createdAtRefresh` is still `true`, but the **reason** differs: the bean itself is now eager; no consumer is needed to pull it in. Lesson: looking only at "created=true" output is not enough to know the cause; you must read the bean definition and graph.

### Try 2 — Put @Lazy on eagerCatalogService

```java
@Bean
@Lazy
EagerCatalogService eagerCatalogService(
        RequiredIndex index, Tracker tracker) {
    return new EagerCatalogService(index, tracker);
}
```

If no other eager bean needs the service and no lookup occurs before the check, both the service and required index can remain uncreated at refresh. However, in this project's `main`, calling `getBean(EagerCatalogService.class)` afterward will create the whole chain.

### Try 3 — Remove @Lazy at deferredConsumer's Injection Point

From:

```java
DeferredConsumer deferredConsumer(
        @Lazy RemoteGateway gateway, Tracker tracker)
```

to:

```java
DeferredConsumer deferredConsumer(
        RemoteGateway gateway, Tracker tracker)
```

Now eager `deferredConsumer` needs the real target, so `remoteGateway`, despite having `@Lazy` on its definition, is still created during refresh. `gateway.createdAtRefresh` becomes `true`. This is the test for the difference between **definition lazy** and **injection-point lazy**.

### Try 4 — Invoke the Proxy in the Constructor

If `DeferredConsumer`'s constructor immediately executes `gateway.send("health")`, it will dereference the proxy when the eager consumer is created. `remoteGateway` is once again created early. A proxy defers target creation **until used**, and cannot keep it deferred past startup if the constructor itself uses the target.

### Try 5 — Change IdleReport to Prototype

```java
@Bean
@Scope("prototype")
IdleReport idleReport(Tracker tracker) {
    return new IdleReport(tracker);
}
```

Each `getBean(IdleReport.class)` call can yield a new instance, so `idle.sameSingleton` changes to `false`. That is a **scope** change, not caused by the lazy annotation. Remember to import `org.springframework.context.annotation.Scope` if testing this.

### Try 6 — Have Another Eager Bean Depend on Gateway

If you add a new eager bean that constructor-injects `RemoteGateway` **without a lazy proxy**, the target is still created during refresh, regardless of `deferredConsumer` having an `@Lazy` injection point. A lazy strategy on **one consumer** cannot control other consumers.

## 12. @Lazy on Consumer vs Lazy on Dependency: Case Matrix

Suppose B is the collaborator and A is the consumer. No third party requires B.

| Consumer A | Definition B | Injection A→B | Is B normally created at refresh? |
| --- | --- | --- | --- |
| Eager singleton | Eager singleton | Direct | Yes |
| Eager singleton | Lazy singleton | Direct | **Yes**, because A needs B |
| Eager singleton | Lazy singleton | Suitable `@Lazy` injection point | Usually **no**, target deferred until proxy is used |
| Eager singleton | Lazy singleton | `ObjectProvider<B>` | Usually **no**, until `getObject()` |
| Lazy singleton | Lazy singleton | Direct | No, if neither A nor B is requested by another bean |
| Lazy singleton | Eager singleton | Direct | Yes, B is eager itself |
| Prototype A required by another eager singleton | Lazy singleton | Direct | Possibly yes, because prototype A is created to be injected and needs B |
| Eager A with `@DependsOn("b")` | Lazy B | No constructor reference | B can still be created before A due to explicit ordering |

Do not treat the table as an absolute contract for every plugin/`FactoryBean`/custom scope/proxy configuration; it describes common regular-bean cases. Custom post-processors or explicit lookups during startup can alter timing.

## 13. @DependsOn Can Force Early Creation of a Lazy Bean

`@DependsOn` is intended to **constrain initialization order**. Example:

```java
@Configuration(proxyBeanMethods = false)
class Config {
    @Bean
    @Lazy
    CacheWarmup cacheWarmup() {
        return new CacheWarmup();
    }

    @Bean
    @DependsOn("cacheWarmup")
    BusinessService businessService() {
        return new BusinessService();
    }
}
```

This is an illustrative example requiring `CacheWarmup` and `BusinessService` classes. If `businessService` is an eager singleton, the BeanFactory must ensure `cacheWarmup` is initialized beforehand per `dependsOn` metadata. A lazy bean can be created early even without being passed as a constructor parameter.

**Key point:** Do not view `@DependsOn` as a way to reduce eager creation. On the contrary, it can **add a mandatory initialization edge**.

### @DependsOn Does Not Replace Dependency Injection

If the service actually needs the rules object in its constructor, declare `BusinessService(Rules rules)` or `@Bean businessService(Rules rules)`. `@DependsOn("rules")` only causes `rules` to be created beforehand; it **does not pass a reference** into the constructor.

### Do Not Use @DependsOn as a Workflow Scheduler

If `CacheWarmup`'s constructor calls a series of external APIs, creating it via `@DependsOn` can pull business side effects into startup. That is a lifecycle/job orchestration issue, not merely a lazy flag question.

## 14. An Eager Singleton Can Pull In a Prototype Bean Early

`prototype` and `lazy` are different. Suppose:

```java
@Bean
@Scope("prototype")
WorkBuffer workBuffer() {
    return new WorkBuffer();
}

@Bean
BatchScheduler batchScheduler(WorkBuffer buffer) {
    return new BatchScheduler(buffer);
}
```

If `batchScheduler` is eager, Spring must create a `WorkBuffer` prototype **to inject into the scheduler** during startup. Spring is not pre-instantiating all prototypes: it only creates the requested dependency.

### Prototype Does Not Automatically Give the Consumer a New Buffer Each Time

A singleton scheduler constructor receives a buffer once and normally holds that same reference. If each job needs a fresh buffer, inject `ObjectProvider<WorkBuffer>` and call `getObject()` for each job, or use a factory with an explicit contract.

### Lazy Flag on a Prototype

`@Lazy` is mainly useful to control pre-instantiation of singleton definitions; prototypes are normally created only when requested anyway. Putting `@Lazy` on a prototype does not turn it into a singleton or alter prototype semantics. A prototype that is a dependency of an eager singleton can still be created.

## 15. Are @Autowired Field and Setter Injection Any Different?

Avoiding constructors does not mean a lazy bean escapes startup.

Field injection example:

```java
@Component
public class OrderFacade {

    @Autowired
    private TaxRules taxRules;
}
```

If `OrderFacade` is an eager singleton, Spring must resolve `@Autowired TaxRules` during the population phase. If the `TaxRules` bean is lazy, the container can still create it to inject into the eager facade.

Setter injection:

```java
@Component
public class OrderFacade {
    private TaxRules taxRules;

    @Autowired
    void setTaxRules(TaxRules taxRules) {
        this.taxRules = taxRules;
    }
}
```

Similarly, Spring needs a suitable collaborator object to invoke the setter. The classes above are **two illustrative versions**; do not place both with the same name in one file.

### When @Lazy Is Placed at the Injection Point

```java
@Autowired
@Lazy
private TaxRules taxRules;
```

or:

```java
OrderFacade(@Lazy TaxRules rules) {
    this.taxRules = rules;
}
```

Spring can pass a lazy-resolution proxy to the injection point when the type supports it. However, **constructor injection** is still generally easier to test and expresses required dependencies more clearly than field injection. Use providers or lazy injection points intentionally rather than switching dependencies from constructor to field just to hide the graph.

## 16. A Lazy Dependency Can Be Triggered Early via a BeanPostProcessor

Spring Framework has multiple extension points during bootstrap:

- `BeanDefinitionRegistryPostProcessor` / `BeanFactoryPostProcessor`.
- `BeanPostProcessor`.
- `FactoryBean` and type lookup.
- Init callbacks such as `@PostConstruct`.
- `SmartInitializingSingleton`.
- ApplicationContext event listeners/lifecycle processors.

A post-processor or startup callback may call `getBean("lazyBean")` or invoke a method on a proxy/provider, causing the lazy target to be created **before external requests arrive**.

### Do Not Call getBean Arbitrarily in a BeanFactoryPostProcessor

BeanFactory post-processors run very early, before all regular BeanPostProcessors are registered. Forcing a business bean to be created at this stage can cause the bean to miss expected AOP/proxy/lifecycle behavior.

A startup issue can result from confusing metadata inspection with instance creation. If you only need to inspect a bean definition, use the definition registry API; do not call `getBean()`.

### SmartInitializingSingleton Does Not Guarantee Every Lazy Bean Is Still Absent

An `afterSingletonsInstantiated()` callback runs after the pre-instantiation pass of regular non-lazy singletons. However, lazy dependencies of eager beans may have already been created during that pass. Thus the callback cannot assert "all lazy beans remain uncreated".

Conversely, a `SmartInitializingSingleton` that is itself lazy and only created later is normally **not** invoked with the end-of-pre-instantiation callback at that late creation time. Do not use it as a per-bean constructor event.

### FactoryBean and Type Introspection

With `FactoryBean<T>`, the container distinguishes the factory object and the product. Some type lookups need to initialize the factory to determine the type, depending on flags/contracts such as `allowEagerInit`. Therefore "just querying bean names by type" is not always 100% side-effect-free in every configuration.

For observing a regular lazy singleton without wanting to create it, `containsSingleton("beanName")` is more appropriate than `getBean()`.

## 17. Performance Impact: Fast Startup or Fast First Request?

Suppose a `RemotePricingClient` bean opens connections, builds thread pools, or loads metadata when its constructor runs. When required by an eager service, the cost remains at **startup** even if the bean carries `@Lazy`.

If you change the injection point to a proxy or provider, the cost shifts to **first use**, which can land squarely on a user's first request.

| Strategy | Startup | First use | Error detection |
| --- | --- | --- | --- |
| Eager bean with direct dependency | Creates dependencies immediately | Usually faster after startup | Fail-fast |
| Lazy definition pulled in by eager consumer | **Still incurs cost at startup** | Usually no need to recreate singleton | Fail-fast for that dependency |
| Lazy injection-point proxy | Consumer initializes while target can remain uncreated | Target resolution + creation cost on first call | Errors may arrive late |
| ObjectProvider lookup at runtime | Provider is usually lightweight | `getObject()` incurs latency and errors | Errors may arrive late |
| Refactor heavy work out of constructor | Lighter construction | Depends on lifecycle/use-case design | Enables proactive startup validation |

**There is no universally optimal choice.** For a required dependency of a core endpoint, failing fast and being immediately ready may outweigh optimizing context creation time. For a rarely used optional feature, lazy sensibly reduces startup cost.

### If Accurate Readiness Is Needed

A successfully created Java object does not prove all external network/DB services are healthy. Have timeouts, health checks, readiness gating, and contract-appropriate connections. Do not confuse singleton creation with distributed system readiness.

### Avoid Putting Business Work into Bean Constructors

An eager bean running `sendWelcomeEmailToAllUsers()` in its constructor can cause side effects on every instance/context/restart. If you later add a lazy proxy, the task merely shifts to the first request rather than becoming a safe solution.

Move business workflows into service methods/startup coordinators with appropriate idempotency, retry, and transaction policies.

## 18. Observing Creation Timing Without Altering the Experiment

### containsBeanDefinition

```java
boolean definitionExists =
        context.getBeanFactory().containsBeanDefinition("remoteGateway");
```

Having a bean definition does not mean the singleton instance has been created.

### containsSingleton

```java
boolean instantiated =
        context.getBeanFactory().containsSingleton("remoteGateway");
```

Checks the singleton cache without asking the BeanFactory to instantiate a new bean. In the main example, before calling the deferred proxy, the result is `false`; after calling `send`, it is `true` for the singleton target.

### getBean

```java
RemoteGateway gateway =
        context.getBean(RemoteGateway.class);
```

This is an **action requesting an instance**. If the lazy target has not been created yet, this call itself can cause it to be created. Calling `getBean` and then checking `containsSingleton` will not prove the target "was already created before lookup".

### Logs and Constructor Counters

Logging in constructors is easy to read visually, but can make output order depend on container internals. To assert accurately, use markers/atomic counters and inspect at the milestones **before refresh**, **after refresh**, **after first use**, and **after close**.

The sample program uses `Tracker` instead of inferring order from logs. In real multithreaded environments, choose `ConcurrentHashMap.newKeySet()`/`AtomicInteger` as needed; the demo's `HashSet` suffices because no worker threads access it concurrently.

### Can a Spring Proxy Be in the Singleton Cache?

Yes. The BeanFactory can expose a proxy instead of the raw target for features like AOP; the "bean reference" a consumer receives may be a proxy. However, a lazy injection-point proxy is a specialized mechanism: it is not necessarily stored under the **target bean name** in the singleton cache before the target is requested. Avoid drawing conclusions solely from the Java class of the reference.

## 19. Common Mistakes

| Symptom | Possible cause | How to resolve |
| --- | --- | --- |
| Annotated `@Lazy` yet constructor still runs at startup | Bean is a dependency of an eager singleton | Identify eager consumers and injection paths |
| `@Lazy` on a bean yet `initMethod` still runs | Bean was created early by another dependency | Inspect graph and callbacks |
| Eager bean created early unintentionally | Missing `@Lazy` on consumer | Choose consumer laziness if the feature is truly optional |
| `@Lazy` at injection point yet target still created during refresh | Consumer constructor/init uses proxy; another consumer requires target directly | Check all call paths and lookups |
| `@Lazy` proxy fails with concrete type | Proxying limitations such as final class/method | Prefer interfaces or providers; review proxy restrictions |
| `containsBean` true makes you think instance was created | API checks resolvability, not cache | Use `containsSingleton` |
| `getBean` alters observation results | Lookup triggers bean creation | Check markers/cache before lookup |
| Bean created in multiple contexts | Singleton scope is per-container | Inspect test/application contexts |
| Prototype created at startup | Eager singleton needs a prototype dependency | Use provider/factory if per-call instances are needed |
| Replaced everything with `@Lazy` yet startup isn't faster | Dependency graph still pulls beans into startup | Analyze graph and high-cost creation points |
| First request slow after lazy refactor | Deferred target construction/resolution | Evaluate trade-off and warm-up/readiness policy |
| Missing lazy target bean, error appears on first request | Proxy/provider defers resolution | Test feature paths; fail fast if dependency is mandatory |
| NoUniqueBeanDefinitionException on provider lookup | Multiple target beans of the same type | Qualifier/Primary/naming policy |
| BeanCurrentlyInCreationException | Circular dependency/early resolution | Fix graph; do not use lazy to hide cycles |
| `@DependsOn` causes lazy bean to be created early | Ordering metadata forces pre-creating target | Inspect `dependsOn` declarations |
| BeanPostProcessor warns bean is not eligible | A bean was created too early in the infrastructure phase | Avoid early `getBean` in post-processors |
| FactoryBean product created unexpectedly early | Eager product/FactoryBean or dependency/type lookup | Inspect `isSingleton`/`isEagerInit`/`allowEagerInit` |
| Startup coordinator using SmartInitializingSingleton hits remote target error | Callback invokes proxy/provider; target starts creating | Manage startup validation separately with explicit timeouts |
| Tests pass locally yet fail in production | Different profiles, beans, component scanning, auto-config | Test the right root/profiles/conditions |

### Step-by-Step Debugging Workflow

1. Obtain the target's **bean name** and the constructors/`@Bean` methods creating it.
2. Check scope: `singleton` or `prototype`?
3. Check the target definition's lazy flag: `@Lazy`, XML `lazy-init`, or global config.
4. Find all **eager singleton consumers** requiring the target via constructor, setter, field, `@Bean` parameter, or `@DependsOn`.
5. Determine whether the target is injected directly, via an `@Lazy` proxy, or via `ObjectProvider`.
6. Check whether constructors/init callbacks invoke the proxy/provider early.
7. Check lookups from post-processors, application events, listeners, and `FactoryBean`.
8. Observe using `containsSingleton`/markers **before** calling `getBean`.
9. Inspect the root cause exception; do not automatically assume a cycle just from seeing `UnsatisfiedDependencyException`.
10. Refactor dependency/use-case boundaries or adjust eager/lazy intentionally; test both startup and first use.

## 20. Testing When a Lazy Bean Is Created

You can add the following assertions to `main` in the Section 10 example while `tracker` and `context` are still active, **before invoking the deferred consumer or looking up idle report**:

```java
if (!tracker.has("requiredIndex")) {
    throw new AssertionError("Eager dependency should create requiredIndex");
}
if (tracker.has("idleReport")) {
    throw new AssertionError("Idle lazy bean created too soon");
}
if (tracker.has("remoteGateway")) {
    throw new AssertionError("Lazy proxy target resolved too soon");
}
if (context.getBeanFactory().containsSingleton("remoteGateway")) {
    throw new AssertionError("Gateway target already in singleton cache");
}
```

After calling `consumer.useGateway("ping")`:

```java
if (!tracker.has("remoteGateway")) {
    throw new AssertionError("Gateway target not created on first use");
}
if (!context.getBeanFactory().containsSingleton("remoteGateway")) {
    throw new AssertionError("Gateway target missing from cache");
}
```

These are **two supplemental snippets**, not standalone Java programs. They clearly express timing boundaries: target is absent before first use, present after using the proxy. Avoid inserting `getBean(RemoteGateway.class)` in between so you do not break the test's assumptions.

### Testing with Multiple Profiles

When dev/prod profiles register different consumers, a lazy target may be pulled in only under one profile:

```text
dev:
  AdminTool (lazy) --> ReportEngine (lazy)
  => ReportEngine can remain deferred.

prod:
  StartupReportService (eager) --> ReportEngine (lazy)
  => ReportEngine is created at startup.
```

Test from the root configuration of each profile, not only isolated bean definitions. Also verify `@Conditional`/`@Profile` values in the right environment.

### Unit Testing Business Logic Without Starting Spring

If `EagerCatalogService` only uses a `RequiredIndex` POJO, a unit test can construct collaborators directly and invoke methods. The "when Spring creates instances" part needs **integration tests with a real context**, because annotations/proxies/lifecycles belong to the container.

### Avoid Assertions Based on Bean Name Counts

`getBeanNamesForType(RemoteGateway.class)` can tell you a bean is **declared for that type** even while the target has not been created yet. A list of names does not prove bean instances exist. To test initialization timing, inspect the cache/constructor markers.

## 21. Circular Dependencies: Can Lazy Solve Them?

Given:

```java
class ServiceA {
    ServiceA(ServiceB b) {
    }
}
class ServiceB {
    ServiceB(ServiceA a) {
    }
}
```

With a constructor cycle A→B→A, the BeanFactory normally cannot create both instances. `@Lazy` on B's **bean definition** does not fix the cycle if eager A still needs to create B. You can use `@Lazy` at an injection point to defer one edge through a proxy in some cases, however:

- The logical cycle still exists.
- The proxy may be dereferenced during constructor/init and recreate the cycle.
- Type/proxy limitations can prevent the workaround from functioning.
- Lifecycles/invariants become harder to reason about.

Prefer extracting a shared interface or moving orchestration to a coordinator:

```text
Before:
ServiceA <----> ServiceB

After:
Orchestrator ---> ServiceA
             \-> ServiceB
```

`spring.main.allow-circular-references` is a Spring Boot option, not plain Spring Framework's standard way of fixing cycles; even when early references are supported for some setter cycles, constructor cycles normally remain unresolvable.

## 22. FactoryBean, AOP, and Cases Requiring Caution

### FactoryBean Is Not the Same as a @Bean Factory Method

`FactoryBean<T>` involves two distinct concepts: the factory object and the product. The BeanFactory may create/inspect the factory object early to learn metadata/types, while the product's eager/lazy semantics depend on `FactoryBean`/`SmartFactoryBean` and consumers.

Do not conclude "if the BeanDefinition is lazy then no related object is created at startup" across all combinations of `FactoryBean`, type introspection, and dependency resolution.

### AOP Proxies and @Lazy Injection-Point Proxies Are Not Identical

A bean with `@Transactional`/AOP can be exposed by Spring through a proxy. An `@Lazy` injection point can also use a proxy, but for a **different reason**: deferring target resolution. One bean can be subject to both mechanisms. Observe target instantiation at the right layer rather than guessing solely from the reference's class name.

### Factory Methods Can Execute Unintended Code

If a Java `@Bean` method both constructs a bean and calls a slow external API, having the target requested by an eager consumer triggers that entire factory method at startup. Moving to a lazy proxy shifts the task to first use; it does not replace timeouts/retries/idempotency.

### Static @Bean and Infrastructure

`BeanFactoryPostProcessor`/`BeanPostProcessor` beans have early creation timing, and `static @Bean` can be appropriate for factory methods supplying certain post-processors to avoid instantiating the configuration object prematurely. This is a separate infrastructure lifecycle area; do not treat `static` as a way to fix ordinary lazy dependencies.

## 23. Spring Boot Global Lazy and Its Consequences

Spring Boot provides the setting:

```properties
spring.main.lazy-initialization=true
```

When enabled, Boot attempts to make many bean definitions lazy to improve startup time. However:

- This is a **Boot option**, not a generic setting automatically read by plain `AnnotationConfigApplicationContext`.
- If a bean remains eager and depends on a lazy bean, that dependency can still be created.
- Some infrastructure beans have exceptions or must run early.
- Configuration errors can be pushed to the first request.
- Beans accessed via proxies/providers may incur extra first-use latency.

**Do not use global lazy as the sole fix** for slow startup caused by business initialization in constructors. Measure real costs, design startup readiness, and preserve fail-fast for mandatory dependencies.

## 24. Exercises with Answers

### Exercise 1 — Distinguishing Definition and Instance

A `@Bean @Lazy Repository repository()` has been registered by Spring. `containsBeanDefinition("repository")` is true. Is that enough to prove the `Repository` constructor has run?

**Answer:** No. The definition existing only proves the container knows how to create it. You must inspect the instance/cache or a marker; do not trigger `getBean()` when you want to measure initial state.

### Exercise 2 — Eager A Needs Lazy B

Bean A is an eager singleton whose constructor requires B; B is a lazy singleton. When the ApplicationContext refreshes, is B created?

**Answer:** Normally yes. To invoke A's constructor, Spring must resolve a B instance per the required dependency.

### Exercise 3 — A Is Lazy

A and B are both lazy; A needs B, but no eager bean needs A or B. After refresh, are they guaranteed to have been created?

**Answer:** No. They can remain deferred. When a caller requests A, Spring creates B to satisfy the dependency and then creates A.

### Exercise 4 — Lazy on Parameter

Eager A receives `@Lazy B b` (injection point) and B is a lazy singleton; interface B is proxiable. When is target B created?

**Answer:** Usually when the proxy is first used; A's constructor can just receive the proxy. However, if A's constructor/init calls a method on the proxy or another consumer needs B directly, B can still be created during startup.

### Exercise 5 — Another Consumer

`CheckoutService` uses a lazy proxy to `RemoteGateway`, but eager `MonitoringService` injects the gateway directly. Is the gateway still deferred after refresh?

**Answer:** Normally no. Eager `MonitoringService` forces target creation. Lazy injection in `CheckoutService` only affects `CheckoutService`'s own dependency edge.

### Exercise 6 — @DependsOn

Eager A has `@DependsOn("b")`; B is a lazy singleton. Can B still be created at startup?

**Answer:** Yes. `DependsOn` requires B to be initialized before A per ordering metadata.

### Exercise 7 — ObjectProvider

An eager consumer holds `ObjectProvider<B>` without calling `getObject()` until method `serve()`. Must lazy B be created at startup?

**Answer:** Not because of that provider edge alone. When `serve()` calls `getObject()`, the target is resolved, unless another consumer created it early.

### Exercise 8 — Observability

You want to know whether lazy bean `remoteGateway` has been created without causing it to be created. Should you call `containsSingleton` or `getBean`?

**Answer:** `containsSingleton("remoteGateway")`. `getBean` can create the object, invalidating the observation condition.

### Exercise 9 — XML

`<bean id="b" class="..." lazy-init="true"/>` and `<bean id="a" ...><constructor-arg ref="b"/></bean>` with A eager. Does swapping the order of the two `<bean>` tags keep B from being created early?

**Answer:** No. Spring relies on the dependency graph, not XML declaration position, to resolve B for A.

### Exercise 10 — Scope

B is prototype, and eager singleton A receives B via constructor. Can B be created at refresh? Does A receive a new B on each business method call?

**Answer:** B can be created to be injected when A initializes. A normally keeps that prototype instance; it does not automatically change per method call. If a fresh B is needed each time, use an appropriate provider/factory.

### Exercise 11 — Missing Bean

An eager consumer accepts `@Lazy PaymentGateway gateway`, yet no `PaymentGateway` target bean exists. Context startup may still succeed in some lazy-proxy scenarios. Should you accept this?

**Answer:** No, if the gateway is a required dependency. Target resolution failure is pushed late. Test the path using the gateway or fail fast proactively per your reliability contract.

### Exercise 12 — Cycle A↔B

Eager A's constructor needs lazy B, and B's constructor needs A. Does merely adding `@Lazy` on B's definition resolve the cycle?

**Answer:** No. A still needs B immediately, and B needs A which is currently in creation. Fix the dependency graph or extract a suitable coordinator/abstraction.

### Exercise 13 — Singleton After First Use

A lazy singleton is created by `getBean` on the first request. A later request fetches the same bean from the context. Does each lookup return a new instance?

**Answer:** No. Lazy does not change singleton identity; lookups within the same container return the same managed singleton.

### Exercise 14 — The Price Paid

A bean takes 800 ms to construct. Using a proxy defers the target. Does the 800 ms cost disappear?

**Answer:** No. It can shift to first-use latency. You must measure and manage user paths/timeouts rather than only optimizing startup metrics.

### Exercise 15 — Callback After Singleton Pre-Instantiation

Does `SmartInitializingSingleton.afterSingletonsInstantiated()` guarantee no lazy bean has been created yet?

**Answer:** No. Lazy beans pulled in by eager dependencies may already have been created during the pre-instantiation phase.

### Exercise 16 — Predicting Output

In the Section 10 example, why is `required.createdAtRefresh=true` while `idle.createdAtRefresh=false`?

**Answer:** `requiredIndex` is a required dependency of eager `eagerCatalogService`; `idleReport` has no eager consumer requesting it.

### Exercise 17 — Observing Proxies

Why is `gateway.hasSingletonBefore=false` even though `deferredConsumer` was created successfully?

**Answer:** The consumer holds a lazy-resolution proxy for `RemoteGateway`; the target singleton `remoteGateway` did not need to be instantiated yet at that point.

### Exercise 18 — Refactoring

An application has an eager controller needing 5 lazy clients, yet only one client is used frequently. Propose a design to reduce startup cost without hiding mandatory dependencies.

**Guided answer:** Keep eager initialization only for the core client requiring fail-fast behavior; for rarely used integrations, inject an interface via an `@Lazy` injection point or a provider at the use-case boundary. The constructor must not dereference the lazy proxy. Write tests for feature paths, configure timeouts/health/readiness for external services, monitor first-use latency, and do not use global lazy to mask missing configuration.

## 25. Project Verification Checklist

- [ ] Distinguished `singleton` scope from `eager`/`lazy` timing.
- [ ] Understood `ApplicationContext.refresh()` proactively creates regular non-lazy singletons.
- [ ] Do not interpret `@Lazy` on a bean definition as a ban against creation during startup.
- [ ] Checked **all eager consumers** of lazy targets.
- [ ] Checked constructor, `@Bean` method parameter, setter, and field injections.
- [ ] Do not confuse `@Lazy` at an injection point with `@Lazy` on a bean definition.
- [ ] When using a lazy proxy, ensured the type is proxiable and constructor/init do not dereference it early.
- [ ] When using a provider, only looked up when needed and handled absence/errors transparently.
- [ ] Do not use provider/optional lookup to silently ignore a mandatory dependency.
- [ ] Do not use `@DependsOn` as a way to keep a bean lazy.
- [ ] Do not expect a prototype never to appear during startup.
- [ ] With `FactoryBean`, distinguished factory instance, product, and eager type lookup.
- [ ] Do not force business beans to initialize early from BeanFactory post-processors.
- [ ] Measured lazy state via `containsSingleton` or markers before first use.
- [ ] Do not call `getBean` when merely asking whether a lazy target has been created.
- [ ] Integration tests cover startup, first use, extra eager consumer, and failure paths.
- [ ] Controlled configuration errors deferred by lazy proxies/providers.
- [ ] Planned for first-use latency and startup readiness.
- [ ] Do not depend on constructor log ordering between independent beans.
- [ ] Kept constructors and init callbacks lightweight without non-idempotent workflows.
- [ ] Do not use lazy merely to mask circular dependencies.
- [ ] Evaluated Boot global lazy exceptions if running on Boot.

## Conclusion

**A bean with `@Lazy` can still be created by a non-lazy dependency** because Spring must fulfill dependencies of eager consumers while `ApplicationContext.refresh()` creates non-lazy singletons.

Three situations to distinguish:

1. **Lazy bean definition + eager consumer with direct injection:** Spring still creates the target at startup.
2. **Lazy injection-point proxy:** the eager consumer can be created with a proxy, while the target is deferred until the proxy is used — unless another path creates it early.
3. **`ObjectProvider<T>`:** the consumer holds the provider and requests the target when needed, suitable when dynamic lookup is intentional.

`@Lazy` does not alter singleton scope, does not turn a required dependency optional, does not eliminate construction cost, and does not fix circular dependencies by itself. Inspect the full bean graph, test with a real context, and measure both **startup** and **first use** before deciding the level of laziness.

## Official Spring Documentation

- [Spring Framework 6.2 — Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-lazy-init.html): lazy mechanism and the case where an eager singleton forces a lazy dependency to initialize.
- [Spring Framework 6.2 — @Lazy Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/Lazy.html): lazy bean definitions, lazy-resolution proxies for injection points, and limitations.
- [Spring Framework 6.2 — Dependency Injection](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-collaborators.html): constructor/property dependency resolution.
- [Spring Framework 6.2 — ObjectProvider API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/ObjectProvider.html): lazy/dynamic lookup.
- [Spring Framework 6.2 — Bean Scopes](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html): singleton/prototype semantics.
- [Spring Framework 6.2 — Bean Dependencies: depends-on](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-dependson.html): ordering metadata.
