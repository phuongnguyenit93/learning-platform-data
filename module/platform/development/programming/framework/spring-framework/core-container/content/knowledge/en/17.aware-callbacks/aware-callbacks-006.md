# Trade-Offs Between Container Convenience and Spring Coupling

## 1. The Design Question: How Much Convenience Is Reasonable?

The Spring Core Container lets beans tap into many conveniences beyond receiving ordinary collaborators: knowing the bean name via `BeanNameAware`, accessing the bean registry via `BeanFactoryAware`, receiving `ApplicationContext` via `ApplicationContextAware`, retrieving dependencies on demand, publishing events, reading resources, or accessing scope metadata. Those capabilities are very useful when building **infrastructure/framework adapters**.

The trade-off is that **the more a business object knows about the container, the more coupled it becomes to Spring and Spring configuration**. A class calling `applicationContext.getBean(PaymentGateway.class)` itself may get the job done today, yet the `PaymentGateway` dependency is no longer visible in its constructor; plain Java unit tests must boot/mock a context or stub lookup calls; and when scopes or configurations change, errors may only surface at runtime.

Guiding principle:

> Let Spring *wire* components together; let business components clearly express what they *need*. Expose a bean to the container only when its actual role genuinely requires container information or behavior.

Not all Spring coupling is bad. A `BeanPostProcessor`, a framework integration adapter, or a component registering handlers by bean name can legitimately implement `Aware`. By contrast, an `OrderCalculator` that simply sums totals, applies discount rules, and calls `TaxService` should normally receive its collaborators through its constructor.

### Three Tiers of Dependencies to Distinguish

1. **Business dependencies**: `CheckoutService` needs `PaymentGateway`. This is a business relationship that must exist whether using Spring or another framework.
2. **Dependencies on framework abstractions/types**: the class uses `ApplicationEventPublisher`, `ResourceLoader`, or `ObjectProvider`. Spring APIs are present, yet the dependency surface remains narrow.
3. **Dependence on the entire container**: the class implements `ApplicationContextAware` and stores `ApplicationContext` to look up arbitrary beans. This is the broadest level of access and requires a concrete justification.

Do not judge coupling merely by annotation count: a class using `@Component` only at the configuration adapter layer can still keep its business logic pure Java; conversely, a class with zero annotations that holds `ApplicationContext` is already deeply coupled to Spring APIs.

## 2. IoC/DI and How Dependencies Shift

**Inversion of Control (IoC)** means the container is responsible for creating and wiring objects, rather than each object controlling the creation of its collaborators itself. **Dependency Injection (DI)** is one way of implementing IoC: dependencies are supplied through constructors, setters, or other injection points.

Compare the two designs:

~~~text
A. Service actively looks up dependencies

CheckoutService ── getBean() ──► ApplicationContext
                                    │
                                    ▼
                               PaymentGateway

B. Dependencies are provided to the service

Composition root (Spring @Configuration)
     │
     ├── creates PaymentGateway
     │
     └── creates CheckoutService(PaymentGateway)
                │
                ▼
           PaymentGateway
~~~

In Model A, having Spring supply `ApplicationContext` to the service is still a form of injection, yet **the service locates its real collaborator itself**, hiding the business dependency: the constructor only says it needs the container. In Model B, `CheckoutService`'s contract explicitly states it needs `PaymentGateway`.

Model B is usually easier to:

- Read: anyone can see the collaborators right in the constructor.
- Test: `new CheckoutService(fakeGateway)` works outside Spring.
- Swap implementations: the application simply changes the `PaymentGateway` binding at the composition root.
- Control lifecycle: the gateway's scope is resolved when Spring creates or supplies the dependency.
- Catch errors early: missing mandatory dependencies typically surface when the container creates the service instead of when a business method branch executes for the first time.

Model A has a real strength: **dynamic lookup at runtime**, selecting beans based on metadata/container state, or supporting an adapter connected to a plugin architecture or bean definitions. Yet if used to replace regular constructor injection everywhere, the code degrades into a **Service Locator**: dependencies scatter across lookup calls and become hard to manage.

## 3. Benefits of the Three Aware Interfaces and Their Costs

### 3.1. `BeanNameAware` — Knowing Container Identity

Spring invokes `setBeanName(String beanName)` when a bean implements `BeanNameAware`. The bean can use its actual registered name for logging, metadata, or infrastructure registries.

~~~java
public final class NamedListener
        implements org.springframework.beans.factory.BeanNameAware {

    private String beanName;

    @Override
    public void setBeanName(String beanName) {
        this.beanName = beanName;
    }

    public String diagnosticName() {
        return beanName;
    }
}
~~~

**Benefit:** automatically obtains the actual name, even when registered via `@Bean(name = "...")` or a custom bean name generator.

**Cost:** the class directly knows a Spring API; it must be Spring-managed and pass through callbacks before the field is valid. Bean names are **deployment metadata**, not necessarily stable business identifiers. Refactoring a bean name can alter output or behavior if code uses the name as a key.

If a service only needs an "order processing channel" or "tenant code", pass them as explicit constructor data:

~~~java
public final class ChannelProcessor {
    private final String channel;

    public ChannelProcessor(String channel) {
        this.channel = channel;
    }

    public String channel() {
        return channel;
    }
}
~~~

The second pattern has no Spring dependency. On the other hand, if infrastructure genuinely needs the bean name to manage a registry, `BeanNameAware` is appropriate.

### 3.2. `BeanFactoryAware` — Retaining Bean Lookup Access

A bean implementing `BeanFactoryAware` receives the `BeanFactory` currently managing it via `setBeanFactory(BeanFactory)`.

~~~java
public class DynamicConverterAdapter
        implements org.springframework.beans.factory.BeanFactoryAware {

    private org.springframework.beans.factory.BeanFactory beanFactory;

    @Override
    public void setBeanFactory(
            org.springframework.beans.factory.BeanFactory beanFactory) {
        this.beanFactory = beanFactory;
    }

    public Converter converter() {
        return beanFactory.getBean(Converter.class);
    }
}
~~~

This is an illustrative class, assuming a `Converter` interface and corresponding bean exist.

**Benefit:** knows which container owns the bean and can look up beans by type/name when operations occur, honoring actual scopes (singleton, prototype, etc.).

**Cost:** any method can introduce hidden dependencies via `getBean`; tests need a fake/mock factory; `NoSuchBeanDefinitionException`, `NoUniqueBeanDefinitionException`, or scope-not-active errors can surface late; readers cannot tell which bean types the service needs merely by looking at its constructor.

If you only need **one type** retrieved on demand, Spring provides `ObjectProvider<Converter>` injected into the constructor. It remains a Spring-specific abstraction, yet it **restricts the lookup surface to `Converter`** instead of handing the entire factory to the bean.

### 3.3. `ApplicationContextAware` — The Broadest Convenience

A bean implementing `ApplicationContextAware` receives `ApplicationContext` via `setApplicationContext(ApplicationContext)`.

~~~java
public class ContextBridge
        implements org.springframework.context.ApplicationContextAware {

    private org.springframework.context.ApplicationContext context;

    @Override
    public void setApplicationContext(
            org.springframework.context.ApplicationContext context) {
        this.context = context;
    }

    public boolean hasBean(String name) {
        return context.containsBean(name);
    }
}
~~~

Beyond bean lookup, `ApplicationContext` offers event publishing, resource loading, i18n message resolution, and context metadata. It is a convenient tool for wiring an adapter/framework extension.

**Cost:** the class depends on a high-level Spring API; it receives a broader API than most business services need, can call `getBean` arbitrarily, and is hard to replace with plain Java. Multiple parent/child `ApplicationContext`s or integration-test contexts invalidate the assumption that "there is only one context across the whole JVM".

An important note: **injecting `ApplicationContext` via constructor or `@Autowired` instead of implementing `ApplicationContextAware` only changes how the context is delivered; it does not eliminate Spring coupling**. You must replace the dependency with a narrower collaborator/abstraction to genuinely reduce coupling.

## 4. Tool Comparison Table

| Way to Receive Dependency/Capability | What the Class Knows About Spring | Explicitness | Plain Java Testability | When Appropriate |
| --- | --- | --- | --- | --- |
| Constructor DI with business interface `PaymentGateway` | Needs no knowledge of Spring | Highest | High, pass fake directly | Default for business services |
| Setter injection with business interface | Can avoid Spring APIs if wired via config | Clear via setter; dependency can be mutated | Fairly good | Optional/reconfigurable dependencies |
| `@Autowired` field | Knows Spring annotation | Less explicit in constructor | Harder when creating plain objects | Certain integration classes; avoid overuse |
| `ObjectProvider<Gateway>` | Knows one Spring API | Clear dependency type, deferred lookup | Needs fake provider or wrapper abstraction | Prototype/lazy/optional runtime lookup |
| `BeanNameAware` | Knows Spring callback | Clear metadata need | Can invoke setter manually, needs integration tests | Infrastructure needing the bean name |
| `BeanFactoryAware` | Knows Spring BeanFactory | Real dependencies can be hidden | Needs fake factory | Container extensions/dynamic registries |
| `ApplicationContextAware` | Knows Spring ApplicationContext | Broad privileges, dependencies easily hidden | Needs fake/mock context | Infrastructure needing broad context capabilities |
| Spring adapter implementing an application-defined interface | Only the adapter knows Spring | Clear business contract | Core easily tested independently | Multi-module/hexagonal architectures |

There is no single absolute winner: **static dependencies** should be injected explicitly; **dynamic dependencies** call for providers/factories; **container metadata** can justify Aware.

## 5. Replacing Direct Bean Lookup with Constructor DI

### Before: Service Locator Inside a Business Service

~~~java
public class ShippingService
        implements org.springframework.context.ApplicationContextAware {
    private org.springframework.context.ApplicationContext context;

    @Override
    public void setApplicationContext(
            org.springframework.context.ApplicationContext context) {
        this.context = context;
    }

    public void ship(Order order) {
        ShippingGateway gateway = context.getBean(ShippingGateway.class);
        gateway.send(order);
    }
}
~~~

This is an illustrative snippet; `Order` and `ShippingGateway` must be defined. The service's constructor claims it **needs nothing**, yet `ship` demands a specific gateway. If the context or gateway is missing, the error only surfaces when the method is called.

### After: Explicit Dependency, Independent Business Class

~~~java
public final class ShippingService {
    private final ShippingGateway gateway;

    public ShippingService(ShippingGateway gateway) {
        this.gateway = java.util.Objects.requireNonNull(gateway);
    }

    public void ship(Order order) {
        gateway.send(order);
    }
}
~~~

Wiring via Java configuration:

~~~java
@Configuration
class ShippingConfig {
    @Bean
    ShippingService shippingService(ShippingGateway gateway) {
        return new ShippingService(gateway);
    }
}
~~~

These are illustrative snippets, not standalone Java files. `ShippingService` needs no Spring imports; annotations appear only at the composition root. Unit tests can pass a fake `ShippingGateway` and verify send counts.

**Trade-off:** the latter approach requires a constructor and bean wiring declaration; the former feels convenient in short snippets yet makes the service hard to test and migrate across frameworks later. As the number of services grows, the maintenance cost of Service Locator usually outweighs a few lines of constructor code.

## 6. When Dynamic Lookup Is Needed: `ObjectProvider` and Dedicated Factories

Some dependencies must be selected or created **at action time**, such as a prototype needing fresh state per job or an optional dependency. Constructor injection of a single singleton target does not always satisfy that need.

### 6.1. Drop Broad BeanFactory, Use a Typed Provider

~~~java
@Service
class ExportCoordinator {
    private final ObjectProvider<ExportTask> taskProvider;

    ExportCoordinator(ObjectProvider<ExportTask> taskProvider) {
        this.taskProvider = taskProvider;
    }

    void export(RequestData input) {
        ExportTask task = taskProvider.getObject();
        task.run(input);
    }
}
~~~

This is an illustrative snippet assuming `ExportTask` is registered with `@Scope("prototype")` when a new instance is needed per call; `RequestData` is a business type with appropriate imports.

`ObjectProvider<T>.getObject()` resolves the bean according to its scope. With a prototype, a normal lookup provides a new instance; with a singleton, it returns the same singleton; if the bean is wrapped in a scoped proxy, the provider may return the proxy rather than the raw target, so you must understand your scope/proxy configuration. **A provider does not turn a singleton into a prototype on its own.**

A provider makes the dependency type explicit in the constructor, yet **the code still depends on a Spring API**. To keep the business core completely independent, define a **dedicated factory interface** in the application layer.

### 6.2. Wrapping Spring Inside an Adapter

Business layer:

~~~java
public interface ExportTaskFactory {
    ExportTask create();
}

public final class ExportCoordinator {
    private final ExportTaskFactory factory;

    public ExportCoordinator(ExportTaskFactory factory) {
        this.factory = factory;
    }

    public void export(RequestData input) {
        ExportTask task = factory.create();
        task.run(input);
    }
}
~~~

Infrastructure adapter:

~~~java
public final class SpringExportTaskFactory implements ExportTaskFactory {
    private final ObjectProvider<ExportTask> provider;

    public SpringExportTaskFactory(ObjectProvider<ExportTask> provider) {
        this.provider = provider;
    }

    @Override
    public ExportTask create() {
        return provider.getObject();
    }
}
~~~

These snippets are architectural patterns requiring `ExportTask`/`RequestData` definitions and appropriate imports. In plain Java tests, the factory can simply be a lambda `() -> new FakeExportTask()` if `ExportTaskFactory` is a functional interface with matching types.

**Real benefit:** the business layer depends on `ExportTaskFactory`, which it owns itself; the infrastructure adapter is the only place aware of `ObjectProvider`. If Spring is later replaced by a manual factory, you update the adapter/composition root without rewriting the core service.

**Cost:** one extra interface and adapter to maintain. Do not introduce a factory abstraction for a simple singleton used directly; abstraction costs are only worth paying when deferred creation or clear module separation is required.

## 7. Choosing the Right API Level Instead of Taking the Entire ApplicationContext

`ApplicationContext` bundles many capabilities. If a class only needs one piece, a narrower interface prevents unintended access:

| Capability Actually Needed | Narrow Spring Interface or Alternative | Notes |
| --- | --- | --- |
| Publish domain/application events | `ApplicationEventPublisher` | Still a Spring API, but only grants publishing access |
| Read files/resources | `ResourceLoader` or `Resource` | Domain core can receive parsed data instead of loading itself |
| Look up localized messages | `MessageSource` | An independent core can define its own `Localizer` interface |
| Select/create beans of a type on demand | `ObjectProvider<T>` / `ObjectFactory<T>` | Lookup scoped to an explicit type |
| Run logic once all eager singletons are ready | `SmartInitializingSingleton` or lifecycle events | Intended for infrastructure/startup orchestration |
| Know actual bean name | `BeanNameAware` | Container metadata, not a business ID |
| Read application configuration | `Environment` or typed configuration object | Domain can receive a record/value object |
| Access arbitrary bean registry/metadata | `BeanFactory` or appropriate extended interface | Usually only justified in container extensions |

A class injecting `ApplicationEventPublisher` is still **coupled to Spring** because the type lives in a Spring package. Yet the coupling surface is far narrower than holding `ApplicationContext` with access to everything. When pure non-Spring unit testing matters, wrap even the publisher in an application-defined interface such as `DomainEvents`.

## 8. Complete Java 17 Example: Comparing Aware, Constructor DI, and ObjectProvider

The example uses **Java 17**, **Spring Framework 6.2.19**, and Maven. It directly illustrates the benefits and trade-offs of three ways to obtain a collaborator. `AwareReceiptService` holds `BeanFactory`/`ApplicationContext` to look up a formatter; `PureReceiptService` simply receives the formatter via constructor, so it can be instantiated with `new` outside Spring; `ProviderReceiptService` receives a narrowly typed provider.

Directory structure:

~~~text
coupling-tradeoffs/
├── pom.xml
└── src/main/java/example/CouplingDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>coupling-tradeoffs</artifactId>
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
~~~

File `src/main/java/example/CouplingDemo.java`:

~~~java
package example;

import org.springframework.beans.factory.BeanFactory;
import org.springframework.beans.factory.BeanFactoryAware;
import org.springframework.beans.factory.BeanNameAware;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.context.ApplicationContext;
import org.springframework.context.ApplicationContextAware;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class CouplingDemo {

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            AwareReceiptService aware =
                    context.getBean(AwareReceiptService.class);
            PureReceiptService pure =
                    context.getBean(PureReceiptService.class);
            ProviderReceiptService provider =
                    context.getBean(ProviderReceiptService.class);

            System.out.println("Aware: " + aware.render(7));
            System.out.println("BeanFactory/context same bean: "
                    + aware.sameFormatter());
            System.out.println("Constructor DI: " + pure.render(7));
            System.out.println("Provider: " + provider.render(8));
        }

        // The following still works WITHOUT a Spring container:
        PureReceiptService plain =
                new PureReceiptService(new BasicReceiptFormatter());
        System.out.println("Plain Java: " + plain.render(9));
    }

    public interface ReceiptFormatter {
        String render(int invoiceId);
    }

    public static final class BasicReceiptFormatter
            implements ReceiptFormatter {
        @Override
        public String render(int invoiceId) {
            return "INV-" + invoiceId;
        }
    }

    // Spring-coupled: both container APIs and lookup live inside the service.
    public static final class AwareReceiptService
            implements BeanNameAware,
                       BeanFactoryAware,
                       ApplicationContextAware {
        private String beanName;
        private BeanFactory factory;
        private ApplicationContext context;

        @Override
        public void setBeanName(String name) {
            beanName = name;
        }

        @Override
        public void setBeanFactory(BeanFactory beanFactory) {
            factory = beanFactory;
        }

        @Override
        public void setApplicationContext(ApplicationContext applicationContext) {
            context = applicationContext;
        }

        public String render(int invoiceId) {
            return beanName + ": "
                    + context.getBean(ReceiptFormatter.class).render(invoiceId);
        }

        public boolean sameFormatter() {
            return factory.getBean(ReceiptFormatter.class)
                    == context.getBean(ReceiptFormatter.class);
        }
    }

    // Business component importing zero Spring APIs.
    public static final class PureReceiptService {
        private final ReceiptFormatter formatter;

        public PureReceiptService(ReceiptFormatter formatter) {
            this.formatter = formatter;
        }

        public String render(int invoiceId) {
            return formatter.render(invoiceId);
        }
    }

    // Still Spring-specific, yet the lookup surface is restricted by type.
    public static final class ProviderReceiptService {
        private final ObjectProvider<ReceiptFormatter> formatters;

        public ProviderReceiptService(
                ObjectProvider<ReceiptFormatter> formatters) {
            this.formatters = formatters;
        }

        public String render(int invoiceId) {
            return formatters.getObject().render(invoiceId);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        public ReceiptFormatter receiptFormatter() {
            return new BasicReceiptFormatter();
        }

        @Bean("awareReceiptService")
        public AwareReceiptService awareReceiptService() {
            return new AwareReceiptService();
        }

        @Bean
        public PureReceiptService pureReceiptService(
                ReceiptFormatter formatter) {
            return new PureReceiptService(formatter);
        }

        @Bean
        public ProviderReceiptService providerReceiptService(
                ObjectProvider<ReceiptFormatter> formatterProvider) {
            return new ProviderReceiptService(formatterProvider);
        }
    }
}
~~~

Run from the `coupling-tradeoffs` directory:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.CouplingDemo
~~~

Stdout **printed by the program itself** (ignoring Maven or environment logger output):

~~~text
Aware: awareReceiptService: INV-7
BeanFactory/context same bean: true
Constructor DI: INV-7
Provider: INV-8
Plain Java: INV-9
~~~

Explanation:

1. `AwareReceiptService` is managed by Spring. `BeanNameAware` supplies `awareReceiptService`; `BeanFactoryAware` supplies the factory; `ApplicationContextAware` supplies the context. When `render(7)` runs after refresh, the context resolves the `ReceiptFormatter` bean and formats the string.
2. `sameFormatter()` compares two lookups: in this configuration `ReceiptFormatter` has the default singleton scope, so the factory and context return **the same instance**. If configured as prototype or with another proxy, identity results may differ, so do not generalize this check across all scopes.
3. `PureReceiptService` only needs `ReceiptFormatter`, and Spring supplies it through the `@Bean` factory method argument. The service code knows nothing about the container.
4. `ProviderReceiptService` holds `ObjectProvider<ReceiptFormatter>` and looks it up when the method executes. The provider respects actual scope; in this example the formatter is a singleton.
5. After the context closes, the code can still execute `new PureReceiptService(new BasicReceiptFormatter())` and run in plain Java. That is direct proof of the business contract's **testability/reusability without Spring**.

The example places nested classes inside one `CouplingDemo.java` file following Java 17 rules. `Config` is a nested `static` class, `@Bean` methods are invoked by the container, and there are no direct calls to methods on config. No `@ComponentScan` annotation is needed because every bean in the demo is registered via `@Bean`.

**What the example does not prove:** that Aware always has worse performance than DI, or that every application must eliminate all Aware usage. It only illustrates **dependency surface and usage style**. Measuring actual performance requires proper benchmarks; architectural choices should prioritize correctness, maintainability, and runtime lookup requirements over minor method-call overhead.

## 9. Testing: Cost Differences Become Clear

### 9.1. Business Service Using Constructor DI

`PureReceiptService` can be instantiated in a simple unit test without Spring's test runner:

~~~java
ReceiptFormatter fake = id -> "TEST-" + id;
PureReceiptService service = new PureReceiptService(fake);
String actual = service.render(123);

if (!"TEST-123".equals(actual)) {
    throw new AssertionError("Wrong receipt: " + actual);
}
~~~

This is an illustrative snippet assuming the two nested types from `CouplingDemo` are imported or placed in the appropriate class/file. A lambda works because `ReceiptFormatter` is a functional interface with a single abstract method.

Characteristics: every test can construct an independent instance, swap stubs effortlessly, and avoid booting a context or mocking `BeanFactory`.

### 9.2. Service Using `ApplicationContextAware`

To unit test `AwareReceiptService` in isolation without a Spring context, the test must create or mock `ApplicationContext`, ensure `getBean(ReceiptFormatter.class)` returns a fake, invoke `setBeanName`/`setBeanFactory`/`setApplicationContext` properly, or spin up a real test context. If one callback is missed, the test can throw a `NullPointerException` that never happens when the container fully manages the bean.

An integration test with `AnnotationConfigApplicationContext` remains useful to confirm **Spring invokes the callbacks properly**, yet you should not force hundreds of business unit tests to boot a context merely because a service used Service Locator.

### 9.3. Providers and Application-Owned Factories

`ObjectProvider` can be faked or stubbed, yet it still forces business tests to understand a Spring API. When the business core accepts a `ReceiptFormatterFactory` defined by its own module, tests only pass a lambda or plain Java factory. That is especially valuable if the core module's build forbids adding `spring-context` to compile dependencies.

## 10. Impact on Module Architecture

A layered architecture can keep Spring at the edges:

~~~text
application-core/
    ReceiptFormatter
    PureReceiptService
    ReceiptFormatterFactory (if dynamic creation is truly needed)

spring-adapter/
    @Configuration
    @Bean definitions
    ObjectProvider adapters
    EventPublisher adapters
    Aware infrastructure components
~~~

Dependency direction:

~~~text
Spring adapter → Interfaces defined by application core
Business core ── does not need ──► org.springframework.*
~~~

**Meaning:** Core depends on its own stable contracts. The Spring adapter depends on core to wire collaborators and supply infrastructure. If startup mechanisms or test environments change later, the core remains untouched.

However, do not turn "avoid coupling" into wrapping every single API in meaningless new interfaces. In a pure Spring application with no intention of switching frameworks, using `ApplicationEventPublisher` directly in an integration adapter/service can be completely reasonable. **The goal is to confine coupling to where it delivers real value**, not to chase a "zero Spring imports" quota at all costs.

## 11. When Aware Is Appropriate

Several cases genuinely require container access:

1. **Infrastructure extensions/registries:** an adapter must register itself under its actual bean name, such as a plugin system integrated with the Spring bean registry.
2. **Container introspection:** a framework component inspects types/scopes/metadata to provide coordination or diagnostic capabilities.
3. **Framework bridges:** integrating a library that does not follow standard DI, needing to pass Spring-managed beans into a third-party container or API.
4. **Dynamic bean name lookup genuinely driven by configuration:** when the bean name is selected in an adapter at runtime, `BeanFactory` can be used at the boundary instead of letting every business service look up beans itself.
5. **Generic tooling:** an infrastructure bean using `ApplicationContext` to provide diagnostic screens, event dispatch, or context-scoped resource management.

These cases share a defining trait: **the class's primary responsibility is interacting with the container or bridging infrastructure**, so knowing Spring is part of its technical contract.

When a class handles specific business logic such as tax calculation, funds transfer, order validation, or pricing, it usually does not need those three Aware interfaces. The less container access a class has, the easier it is to read, test, and replace.

## 12. Runtime Lookup and Lifecycle Risks

### 12.1. Hidden Dependencies

A constructor `ReportService(ApplicationContext context)` does not reveal that the business service needs `InvoiceRepository`, `CurrencyService`, and `AuditPublisher`. Hidden dependencies only surface when reading methods containing `getBean`, sometimes only inside an error branch. Static analysis and code reviews struggle to inspect the full bean graph.

Moving real dependencies into the constructor clarifies the contract. If only one deferred bean lookup is needed, inject `ObjectProvider<SpecificType>` to specify the type explicitly.

### 12.2. Runtime Lookups Can Fail Late

`getBean(Type.class)` can fail due to a missing bean, multiple beans of the same type, insufficient qualifiers, or an inactive scope. If executed only on a rare business branch, the error appears much later than creating the bean via constructor injection of mandatory dependencies. This does not guarantee all constructor DI catches every error at app startup: lazy beans can still instantiate later, yet the dependency graph remains explicitly declared.

### 12.3. Lookup Does Not Mean "New Object"

For a singleton, repeated `getBean()` calls return the same instance. For a prototype, each direct target lookup normally creates a new instance. For request/session scope, the result depends on scope context; a request-scoped bean cannot be used arbitrarily from a background thread with no active request. For a scoped proxy, you may get the same proxy while the target is resolved per invocation.

Using Aware/`BeanFactory` does not change bean scope semantics. You must understand whether the bean you retrieve is a raw target, a proxy, or a factory product.

### 12.4. Spring-Managed Objects vs. Plain Java Objects

Aware callbacks are only invoked by Spring when the object is created/managed by the container and passes through proper processing. Plain Java `new AwareReceiptService()` does not automatically trigger `setApplicationContext`. Do not use a static `"ApplicationContextHolder"` to turn every object into a global service locator; it introduces shared mutable state, stale contexts after shutdown, and hidden dependencies.

### 12.5. Container Still Mid-Initialization

`setBeanFactory` and `setApplicationContext` belong to the lifecycle **before the bean is fully initialized**. Calling other beans or running heavy tasks right inside a callback can trigger premature initialization, circular dependencies, initialization deadlocks, or expose raw objects before AOP proxies are applied. Callbacks should accept/store infrastructure references and return quickly; work depending on the full context belongs in an appropriate hook.

### 12.6. AOP, `@Transactional`, and Self-Invocation

If a service calls `this.transactionalMethod()` directly inside an Aware setter or `@PostConstruct`, it does not go through the normal Spring AOP proxy; `@Transactional` may not apply. Accessing the container just to "fetch my own proxy" inside a callback is a confusing design smell that can pull an incomplete bean. Move transactional business logic to a collaborator invoked from an appropriate post-initialization point.

### 12.7. Closing Contexts and Holding References Too Long

If a background thread retains `ApplicationContext` and attempts `getBean()` after `context.close()`, it is calling expired infrastructure. With parent-child contexts, a child context can close while the parent remains alive. Avoid letting business classes hold JVM-wide context references; ownership and lifecycle must remain clear in adapters.

## 13. How to Evaluate Coupling During Code Review

Do not just ask "Does this file import Spring?". Answer concretely:

- Can the class be instantiated with `new` using test-supplied dependencies?
- If a mandatory dependency is missing, does the constructor/bean definition make that obvious, or is the failure deferred until `getBean()` inside a business method?
- Does the class genuinely need the bean name, metadata, or event context, or simply a collaborator?
- Do unit tests have to fake an entire `ApplicationContext` just to return a single simple bean?
- Is runtime lookup intentional for scope/dynamic selection, or merely a shortcut to avoid adding a constructor parameter?
- Could the lookup instantiate beans while the container is still initializing or when a web scope is inactive?
- If changing from `ApplicationContextAware` to injecting `ApplicationContext` in the constructor, has coupling actually decreased? **No**, if the class still operates on the context.
- Can bean lookups be placed at the composition root/adapter, passing business interfaces into the core?
- If adding a new abstraction, does it represent a real domain concept, or merely mirror a framework API unnecessarily?

If the core already contains numerous `ApplicationContextHolder.getBean` calls or services routinely request arbitrary bean names, treat that as a **sign of Service Locator leaking into business logic**. Prioritize refactoring flows that change frequently, are hard to test, or suffer runtime lookup failures first.

## 14. Practical Refactoring Workflow

### Step 1 — Inventory Hidden Dependencies

Find every `getBean`, `getBeansOfType`, static context holder, or `BeanFactoryAware`/`ApplicationContextAware` implementation. For each location, record the **looked-up type/name**, the reason for dynamic lookup, and the actual scope.

### Step 2 — Convert Static Lookups into Constructor Arguments

If a service always needs `PaymentGateway` and has no runtime implementation switching, constructor `Service(PaymentGateway gateway)` is the simplest solution. Let Spring pick the implementation via `@Primary`/`@Qualifier` in configuration when needed.

### Step 3 — Keep Deferred Lookups Explicitly Typed

If a fresh prototype is needed per job, inject `ObjectProvider<Task>` or an application-defined factory. Obtain one instance per job and hold it in a local variable if state must persist across multiple methods. Do not configure a prototype proxy and unknowingly call multiple methods expecting them to hit the same target.

### Step 4 — Isolate Broad Context Infrastructure into Adapters

If reading resources, publishing events, or querying bean metadata is required, consolidate it into a Spring adapter. Let the business core accept dedicated interfaces like `TemplateContentProvider` or `DomainEvents`. This enables context-free testing with fakes.

### Step 5 — Remove Unused Spring Dependencies

Once the core accepts abstractions/POJOs, remove the Aware interfaces and redundant fields/lookups from that class. In multi-module builds, consider configuring dependencies so the core module does not require `spring-context` at compile time.

### Step 6 — Verify Behavior and Lifecycle

Write plain Java unit tests for the core; write integration tests using `ApplicationContext` for adapters/wiring. Test missing beans, multiple implementations, per-job prototype creation, inactive request scope, context closing, and error handling. Do not change scopes during refactoring unless business requirements demand it.

## 15. Common Decisions

| Scenario | Preferred Decision | When to Reconsider? |
| --- | --- | --- |
| `InvoiceService` needs a fixed `InvoiceRepository` | Constructor DI | Truly dynamic repository routing |
| `OrderService` needs a component name for logging | Explicit configured component name/label | Framework registry requires actual bean name → `BeanNameAware` |
| Consumer wants to publish events | Inject `ApplicationEventPublisher` or domain event adapter | Infrastructure needs multiple context capabilities simultaneously |
| Singleton wants a prototype per job | `ObjectProvider<Task>` or factory adapter | Must select beans by dynamic name |
| Code reads a template from classpath | Inject `Resource`/`ResourceLoader` or content provider | Framework adapter needs broad context resource semantics |
| Code needs i18n | `MessageSource` or domain `Localizer` | Framework component integrates across the whole context |
| Generic Spring diagnostic console | `ApplicationContextAware` may be justified | Should restrict operations and lifecycle |
| Plugin registry selects beans by runtime name | BeanFactory inside an adapter | Can inject `Map<String, Plugin>` when plugin set is finite |
| Testing a pure calculation | No Spring test context needed | Use integration tests only for wiring |
| Legacy static context holder used everywhere | Move lookups toward boundaries | Avoid risky big-bang refactoring across the entire project |

## 16. Self-Check Questions

**Question 1.** Does replacing `ApplicationContextAware` with constructor `MyService(ApplicationContext context)` eliminate Spring coupling?

**Answer:** No. It only changes how the context is passed; the code still references Spring types and retains arbitrary lookup access.

**Question 2.** Why is constructor `CheckoutService(PaymentGateway gateway)` easier to test than `CheckoutService(ApplicationContext context)`?

**Answer:** The business dependency is explicit; tests can pass a fake gateway directly without building or mocking a container API just to return the gateway.

**Question 3.** Does `ObjectProvider<ReportTask>` always return a new instance?

**Answer:** No. It depends on the resolved bean's scope: singletons are reused, prototypes create a new instance per lookup, and scoped proxies have their own semantics.

**Question 4.** Should an adapter registering plugins by actual bean name be forbidden from using `BeanNameAware`?

**Answer:** No. For infrastructure that needs the exact bean metadata, `BeanNameAware` is a reasonable tool. Just avoid pulling it into business code that does not need Spring bean names.

**Question 5.** Does injecting `ApplicationEventPublisher` instead of `ApplicationContext` completely remove Spring coupling?

**Answer:** No. Both belong to Spring APIs, though publisher has a narrower surface; if you want pure Java core code, define an application interface such as `DomainEvents` and implement it in a Spring adapter.

**Question 6.** Why shouldn't you call `context.getBean(...)` to start multiple workers inside `setApplicationContext`?

**Answer:** The callback runs mid-way through bean creation; doing so can trigger premature dependency creation, circular dependencies, incomplete AOP/proxies, and block startup. Use a dedicated lifecycle hook like `SmartLifecycle` for start/stop behavior.

**Question 7.** A service uses constructor DI yet is annotated with `@Service`. Does it still depend on Spring?

**Answer:** The class still depends on a Spring annotation in source code, yet its business methods and collaborators can still be tested with `new` if the constructor takes plain Java interfaces. To remove compile-time dependency entirely, move annotations/bean registration to the composition root.

**Question 8.** What capability does `BeanFactoryAware` offer that direct constructor DI does not provide out of the box?

**Answer:** It lets an infrastructure component access the bean-managing factory and look up beans based on metadata/names at runtime. That is valuable for adapters/framework extensions, yet it widens coupling and hides dependencies.

## 17. Application Checklist

- Have you distinguished **business dependencies**, **narrow Spring capabilities**, and **container-wide APIs**?
- Do mandatory collaborators appear explicitly in the constructor?
- Does code use `Aware` only when Spring metadata or infrastructure is genuinely required?
- Where deferred lookup is needed, is a scope-appropriate provider/factory used?
- Can the business core be tested with POJOs/fakes without booting `ApplicationContext`?
- Have you avoided static `ApplicationContext` holders and bean lookups scattered across business logic?
- Have you distinguished coupling from **how context is injected** vs. coupling from **which API type is used**?
- For proxied beans, do you understand lookup timing and scope-based target semantics?
- Have you avoided dynamic bean calls or heavy work while Aware callbacks are running?
- Do adapters have clear lifecycle/ownership when the context closes?
- Does every extra abstraction interface carry real business meaning rather than adding boilerplate?

## 18. Official Documentation

- [Spring Framework Reference — ApplicationContextAware and BeanNameAware](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html#beans-factory-aware)
- [Spring Framework Reference — BeanFactory API](https://docs.spring.io/spring-framework/reference/core/beans/beanfactory.html)
- [Spring Framework Reference — Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Spring Framework Reference — Annotation-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config.html)
- [Spring Framework Reference — Container Extension Points](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html)
- [Spring Framework Reference — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Spring Framework Javadoc — ApplicationContextAware](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationContextAware.html)
- [Spring Framework Javadoc — BeanFactoryAware](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/BeanFactoryAware.html)
