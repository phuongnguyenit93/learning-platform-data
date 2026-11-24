# Dependency Graphs and Container Responsibilities — Spring Framework Core Container

## 1. Goal: Viewing an Application as a Graph

A Java application typically consists of many collaborating objects: services use repositories, payment processors use pricing calculators and audit loggers. A **dependency graph** represents *which component needs which component*. The Spring **IoC container** reads bean configuration and then creates, wires, and manages those components.

After this lesson, you will be able to:

- Draw multi-layer, multi-branch graphs where multiple consumers share a dependency, and identify edge directions.
- Distinguish a **bean graph** from a **method call graph** and `extends`/`implements` relationships.
- Explain the responsibilities of `BeanFactory`, `ApplicationContext`, bean configuration, dependency resolution, and injection.
- Reason about eager singletons, lazy beans, prototypes, constructor circular dependencies, and `@DependsOn` without confusing creation order with edge direction.
- Run a standalone example with **Spring Framework 6.2.19 + Java 17+**, Maven or `javac`/`java`, and verify stdout.

This lesson focuses on the **wiring graph and container management boundaries**. A dependency can be passed in plain Java without Spring; Spring **automates the assembly step based on configuration**.

## 2. Nodes, Edges, and Arrow Direction

In this lesson, **A → B** means **bean A depends on bean B**. It does *not* mean A is created before B, nor that A always calls B on every request, and it says nothing about type inheritance.

Example:

- `CheckoutService` needs `PriceService` to calculate totals.
- `CheckoutService` needs `AuditTrail` to record events.
- `PriceService` needs `ProductCatalog` to get unit prices.
- A bean named `productCatalog` provides the `FixedCatalog` implementation for the `ProductCatalog` interface.

~~~mermaid
flowchart LR
    Checkout["checkoutService: CheckoutService"]
    Price["priceService: PriceService"]
    Audit["auditTrail: AuditTrail"]
    Catalog["productCatalog: ProductCatalog / FixedCatalog"]
    Checkout --> Price
    Checkout --> Audit
    Price --> Catalog
~~~

Looking at the structure:

~~~text
checkoutService
├── priceService
│   └── productCatalog
└── auditTrail
~~~

When adding `ReportingService → ProductCatalog`, both ReportingService and PriceService can use **the same bean** `productCatalog` if that bean is a singleton in the same context. Because multiple edges can point to one node, the accurate model is a **graph**, not just a tree.

**Read these three relationship kinds accurately:**

| Relationship | Question answered | Example |
| --- | --- | --- |
| Bean dependency graph | Which bean needs which bean? | `priceService → productCatalog` |
| Runtime call graph | Which method calls which method? | `PriceService.total() → ProductCatalog.unitPrice()` |
| Type relationship | Which class implements/extends which type? | `FixedCatalog implements ProductCatalog` |

Calling a static utility, creating a temporary object with `new`, or calling internal methods **does not automatically create a bean graph edge**. Likewise, a dependency edge can exist even if a particular execution path never calls a method on the dependency.

### Are Nodes Bean Definitions or Objects?

Separate these three:

1. **Bean definition:** metadata Spring uses to know the name, factory/bean type, scope, and initialization/configuration rules.
2. **Bean instance:** the actual object created/returned by the container when needed.
3. **Java type:** the interface or class declared at the injection point.

A `singleton` bean definition typically maps to one instance per container; a `prototype` bean definition can lead to many instances. When AOP proxies are involved, the injected object may be a **proxy**, not simply the original implementation class. Therefore, the *definition graph* does not always align 1-to-1 with the *instance graph at a given moment*.

## 3. What Is the Container Responsible For?

Spring does not require a manually entered graph diagram. It reads configuration and injection points to determine which collaborators are needed.

**Core logical steps:**

1. **Register bean definitions:** from `@Configuration`/`@Bean`, component scanning (`@Component`, `@Service`, `@Repository`, ...), XML, or programmatic APIs.
2. **Process configuration and metadata:** capture declared types, names, scopes, conditions, and related configuration post-processors.
3. **Resolve dependencies:** for constructor/factory-method arguments, setter/field injection where applicable, find candidate beans by type, qualifier, primary, and Spring rules.
4. **Create and configure beans:** create required dependencies, invoke factories/constructors, assign dependencies, and apply corresponding extension points.
5. **Manage lifecycle:** run initialization hooks, retain beans per scope, supply beans through the context, and invoke appropriate destruction hooks when the context/scope closes.
6. **Report configuration errors:** missing beans, ambiguous multiple candidates, initialization cycles, or errors directly inside factories/constructors.

**Not** automatically the container's responsibility: designing pricing logic, approving orders, handling business workflows, validating domain data, or guaranteeing thread safety for singletons holding mutable state. Spring has other modules that assist with some of those concerns, but the IoC container alone **does not know your business rules**.

### BeanFactory and ApplicationContext

- `BeanFactory` is the core contract for looking up and working with beans.
- `ApplicationContext` extends those capabilities: convenient lifecycle integration, events, message resources, environment configuration, and other mechanisms; it is the usual choice when using Spring.
- `AnnotationConfigApplicationContext` is an implementation that can create a context directly from Java configuration classes, without Spring Boot or a Servlet container.

Example declaration:

~~~java
@Bean
PriceService priceService(ProductCatalog catalog) {
    return new PriceService(catalog);
}
~~~

This is just an **illustrative snippet inside a configuration class**. The parameter `ProductCatalog catalog` declares a dependency of the `priceService` bean. The container resolves a bean for that parameter and then invokes the factory method.

**Registration timing differs from instantiation timing:** a bean definition may already be known before its bean instance is created; by default many non-lazy singletons are instantiated during `ApplicationContext.refresh()`, whereas lazy/prototype beans may wait until retrieval.

## 4. Standalone Java 17+ Example: A Multi-Layer Graph

Uses **Spring Framework 6.2.19**, Maven, and JDK 17+. No Spring Boot, database, or web server is needed. On the first run, Maven may need Internet access to download JARs.

~~~text
bean-graph-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── DependencyGraphDemo.java
~~~

### 4.1. File `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bean-graph-demo</artifactId>
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
                    <mainClass>demo.DependencyGraphDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Maven automatically resolves transitive dependencies of `spring-context`; copying only `spring-context.jar` onto the classpath is typically not enough.

### 4.2. File `src/main/java/demo/DependencyGraphDemo.java`

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class DependencyGraphDemo {
    private DependencyGraphDemo() {}

    public interface ProductCatalog {
        int unitPrice(String sku);
    }

    public static final class FixedCatalog implements ProductCatalog {
        @Override
        public int unitPrice(String sku) {
            if (!"BOOK".equals(sku)) {
                throw new IllegalArgumentException("unknown sku");
            }
            return 15;
        }
    }

    public static final class PriceService {
        private final ProductCatalog catalog;

        public PriceService(ProductCatalog catalog) {
            this.catalog = Objects.requireNonNull(catalog);
        }

        public int total(String sku, int quantity) {
            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }
            return Math.multiplyExact(catalog.unitPrice(sku), quantity);
        }
    }

    public static final class AuditTrail {
        private final List<String> events = new ArrayList<>();

        public void record(String event) {
            events.add(event);
        }

        public List<String> snapshot() {
            return List.copyOf(events);
        }
    }

    public static final class CheckoutService {
        private final PriceService prices;
        private final AuditTrail audit;

        public CheckoutService(PriceService prices, AuditTrail audit) {
            this.prices = Objects.requireNonNull(prices);
            this.audit = Objects.requireNonNull(audit);
        }

        public String confirm(String sku, int quantity) {
            int total = prices.total(sku, quantity);
            String event = sku + " x " + quantity + " => " + total;
            audit.record(event);
            return event;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public ProductCatalog productCatalog() {
            return new FixedCatalog();
        }

        @Bean
        public AuditTrail auditTrail() {
            return new AuditTrail();
        }

        @Bean
        public PriceService priceService(ProductCatalog catalog) {
            return new PriceService(catalog);
        }

        @Bean
        public CheckoutService checkoutService(
                PriceService prices, AuditTrail audit) {
            return new CheckoutService(prices, audit);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            CheckoutService checkout =
                    context.getBean(CheckoutService.class);
            AuditTrail audit = context.getBean(AuditTrail.class);

            System.out.println("confirm=" + checkout.confirm("BOOK", 2));
            System.out.println("audits=" + audit.snapshot());
            System.out.println("catalogSingleton=" +
                    (context.getBean(ProductCatalog.class) ==
                     context.getBean(ProductCatalog.class)));
            System.out.println("priceSingleton=" +
                    (context.getBean(PriceService.class) ==
                     context.getBean(PriceService.class)));
            System.out.println("priceRegistered=" +
                    context.containsBean("priceService"));
        }
    }
}
~~~

There is **one top-level public class** with supporting classes/interfaces nested inside, so the filename is `DependencyGraphDemo.java`. `@Configuration(proxyBeanMethods = false)` works because factory methods **do not directly call each other**; Spring supplies collaborators through method parameters. If you call `priceService(productCatalog())` directly inside `@Bean` in this mode, you are making a regular Java call, which may create instances outside the desired wiring/singleton behavior.

### 4.3. Running with Maven

In the `bean-graph-demo` directory:

~~~bash
java -version
mvn -version
mvn -q clean compile exec:java
~~~

**Exact 5 stdout lines printed by `main`:**

~~~text
confirm=BOOK x 2 => 30
audits=[BOOK x 2 => 30]
catalogSingleton=true
priceSingleton=true
priceRegistered=true
~~~

Output from `java -version`, `mvn -version`, and Maven/Spring logging (if configured) **does not count toward the five application stdout lines**.

### 4.4. Running Directly with `javac` and `java`

The code needs a classpath containing Spring and its transitive libraries. From the project root, have Maven build the classpath:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

**Linux/macOS (bash/zsh):**

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -cp "$(cat classpath.txt)" \
  -d out src/main/java/demo/DependencyGraphDemo.java
java -cp "out:$(cat classpath.txt)" demo.DependencyGraphDemo
~~~

**Windows PowerShell:**

~~~powershell
$deps = (Get-Content -Raw classpath.txt).Trim()
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -cp "$deps" -d out src/main/java/demo/DependencyGraphDemo.java
java -cp "out;$deps" demo.DependencyGraphDemo
~~~

The classpath separator is `:` on Unix and `;` on Windows. Both run methods execute **the same main class** and produce the exact same five output lines. If `javac` reports `package org.springframework... does not exist`, check the classpath/JARs rather than changing the DI code.

## 5. Reading the Graph from Factory Methods

| Bean name | Bean type | Direct dependency edges |
| --- | --- | --- |
| `productCatalog` | `ProductCatalog` (actual object `FixedCatalog`) | None |
| `auditTrail` | `AuditTrail` | None |
| `priceService` | `PriceService` | `productCatalog` |
| `checkoutService` | `CheckoutService` | `priceService`, `auditTrail` |

The container follows the relationships:

1. It discovers the factory methods exposed by `@Bean`.
2. When `priceService` is needed, it must have an eligible `ProductCatalog`; the sole candidate is `productCatalog`.
3. When `checkoutService` is needed, it must have eligible `PriceService` and `AuditTrail` beans.
4. Two `context.getBean(ProductCatalog.class)` calls in the same context return the same default **singleton** bean: `catalogSingleton=true`.
5. `CheckoutService.confirm(...)` calculates the price and records the audit. The container **does not invoke `confirm` business logic automatically**; it only assembles the objects for the application to use.

### A Valid Graph Does Not Mean a Fixed Instantiation Order

With an **acyclic** graph where all dependencies are created before their consumers, you can think in terms of **topological order**: catalog is needed before price, price and audit are needed before checkout. However:

- `productCatalog` and `auditTrail` are independent, so **there is no business rule** forcing which one is created first.
- Declaration order in diagrams or `@Bean` method names **is not a general contract** for startup order.
- Lazy, prototype, and on-demand creation mechanisms can change when objects are created.
- Graphs can contain **cycles**; therefore you must not assume every dependency graph is a DAG.

Do not write code that depends on two **unrelated** singletons always being instantiated in an incidental order observed on one machine.

## 6. Circular Dependencies and How to Handle Them

An acyclic graph is straightforward to build: the container resolves dependency nodes and then creates the consumer. A classic **constructor cycle**:

~~~java
final class A {
    A(B b) {}
}
final class B {
    B(A a) {}
}
~~~

This is only an **illustrative snippet**, not a standalone Spring program. If A and B are registered as beans, each requiring the other in its constructor, creating A requires B while creating B requires A: A → B → A. Spring typically reports an error, such as `BeanCurrentlyInCreationException` (possibly wrapped inside another exception chain).

**Proper fix:** revisit each class's responsibilities, break the ownership cycle, introduce an abstraction or events where genuinely appropriate, and make dependencies clear. Randomly switching constructor injection to field/setter injection just to dodge the error can yield incompletely initialized beans without fixing the architecture.

Some setter cycles can be resolved via early-reference mechanisms in certain configurations, but this is **not guaranteed in all cases** and is not a reason to design intentional circular dependencies.

## 7. Direct Dependencies, `@DependsOn`, and Initialization Order

If B actually **uses object A**, declare A as a dependency via constructor/factory arguments. Occasionally, however, a bean requires an *initialization side effect* of another bean without taking a reference to it. In that case, `@DependsOn` can be used:

~~~java
@Bean
@org.springframework.context.annotation.DependsOn("auditBootstrap")
public AuditTrail auditTrail() {
    return new AuditTrail();
}
~~~

This is an illustrative example and **does not replace the `auditTrail()` method in the runnable program**. It is meaningful only if a bean named `auditBootstrap` is registered. The container ensures the named bean is initialized before `auditTrail`, **without injecting it** as a parameter.

For singleton beans, `depends-on` also affects destruction: the **dependent** bean is destroyed before the bean it **depends on**. Do not use `@DependsOn` as a substitute for a real dependency or to mask a flawed design.

**Do not use `@Order` to force all singletons to initialize in sequence either.** `@Order` generally applies to ordering components within supported collections/mechanisms, not as a general startup-order rule.

## 8. Missing Beans, Multiple Candidates, and Deferred Dependencies

If an injection point requests `ProductCatalog`:

- **No candidate bean:** Spring cannot finish creating the consumer (you may see `NoSuchBeanDefinitionException` / `UnsatisfiedDependencyException`). Check bean registration config, component scans, conditions, profiles, and declared bean types.
- **Multiple candidates:** Spring cannot determine a unique choice (`NoUniqueBeanDefinitionException`). Use `@Primary`, `@Qualifier`, or adjust configuration to eliminate ambiguity when the contract requires a single bean.
- **Multiple beans genuinely needed:** depending on the problem, inject `List<ProductCatalog>`, `Map<String,ProductCatalog>`, or query via `ObjectProvider<ProductCatalog>`.

**Illustrative snippet, not standalone because `OtherCatalog` is not declared:**

~~~java
@Bean ProductCatalog firstCatalog() { return new FixedCatalog(); }
@Bean ProductCatalog secondCatalog() { return new OtherCatalog(); }
~~~

Two beans sharing an interface can make a single-valued injection point ambiguous unless an appropriate resolution rule is present. Never assume the container can guess which implementation matches business intent.

### How Scopes Affect the Instance Graph

| Scope/mechanism | Effect |
| --- | --- |
| `singleton` (default) | One bean instance per bean definition within a context; not JVM-wide |
| `prototype` | Container creates a bean each time a bean of that definition is requested |
| Prototype injected directly into a singleton | Usually resolved when **the singleton is created**; no new prototype is produced on each method call |
| `@Lazy` | Can defer bean creation until needed; does not remove the logical dependency edge |
| `ObjectProvider<T>` | Allows code to retrieve beans later on demand; suitable when dynamic per-operation resolution is desired |
| Web request/session scope | Requires an appropriate web environment, not available in plain Java contexts |

If you want a fresh prototype on every operation inside a singleton, design a per-use instance lookup mechanism (such as a provider), **not just putting a scope annotation on the target bean**.

### The Container Does Not Automatically Manage All Java Objects

An instance created with `new` outside the container is not automatically injected, does not receive callbacks, and is not managed as a bean. You can construct the same graph manually:

~~~java
ProductCatalog catalog = new FixedCatalog();
AuditTrail audit = new AuditTrail();
PriceService prices = new PriceService(catalog);
CheckoutService checkout = new CheckoutService(prices, audit);
~~~

The snippet above is **only an illustration within the scope of the demo classes**, not a standalone runnable file. This is still dependency injection in terms of design; Spring provides registration, resolution, and lifecycle mechanisms instead of forcing you to wire every object by hand.

## 9. Bean Lifecycle and Developer Responsibilities

| Usually managed by the container | Application responsibility |
| --- | --- |
| Registering configuration and bean definitions | Splitting classes with clear responsibilities, choosing abstractions and contracts |
| Selecting matching injection candidates | Declaring required dependencies openly, preferring constructor injection |
| Instantiating/configuring/post-processing managed beans | Writing pricing logic, audit recording, validation, and business error handling |
| Appropriate scope/lifecycle callbacks | Managing external non-Spring resources, shared state, and thread safety |
| Supplying beans by type/name and closing context | Choosing entry points, calling business methods, and shutting down cleanly |

For `@Bean` methods with init/destroy callbacks or beans implementing lifecycle interfaces, the container invokes the appropriate callbacks. However, not all beans are destroyed identically: for example, prototypes are created by the container, yet the container **does not manage their full destruction after handing them to the caller**. For singletons, the context typically runs destruction when closed.

Do not assume a singleton bean can hold per-request information in mutable fields without synchronization; multiple threads/callers can share the same instance concurrently.

## 10. Debugging When Graph Wiring Fails

| Symptom | Possible cause | Investigation steps |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` or `UnsatisfiedDependencyException` | Required dependency has no candidate | Check names/types/scan/packages/profiles and `@Bean` methods |
| `NoUniqueBeanDefinitionException` | Multiple candidates of the same type | Use qualifier/primary or fix the graph |
| `BeanCurrentlyInCreationException` | An initialization cycle | Trace A→B→…→A and revisit the design |
| Object created with `new` is not injected | Object is not managed by Spring | Retrieve the bean from context or wire manually via DI |
| Lazy bean fails on first use | Deferred wiring error | Trace the dependencies of the just-requested bean |
| Prototype not fresh on every call to a singleton | Dependency was injected once | Use a provider/lookup if a fresh instance is needed per call |
| Trying to force order between unrelated beans | Confusing declaration order with dependency order | Express real dependency edges or intentional `@DependsOn` |
| Context refresh fails | An eager singleton failed during creation | Inspect the `Caused by` chain to find the root dependency |

**Diagnostic workflow:**

1. Identify the entry-point bean the application is requesting.
2. Trace edges from constructor/factory method parameters; note which concrete bean each interface maps to.
3. Determine which bean has missing/duplicate candidates; do not look only at the outer wrapper exception.
4. Look for cycles, including init-only relationships like `@DependsOn`.
5. Check scopes, `@Lazy`, and providers that might defer resolution.
6. Read the root cause in `Caused by` or the stack trace of the failing bean.
7. Fix dependency registration or design, and re-run the example checking expected output.

Do not swallow all container startup errors and continue running with null dependencies; these are normally **configuration errors that should be fixed explicitly**.

## 11. Behavioral Testing vs. Wiring Testing

Two complementary test types:

- **Unit test:** construct the service directly with a fake `ProductCatalog`, without Spring; verify `PriceService.total` has the right logic.
- **Wiring integration test:** create `AnnotationConfigApplicationContext(AppConfig.class)` and call `getBean(CheckoutService.class)` to confirm configuration registers all dependencies without ambiguity and with the right scopes.

The following snippet is **only an illustration used inside a method/class with access to the nested types**:

~~~java
ProductCatalog fake = sku -> 8;
PriceService prices = new PriceService(fake);
System.out.println(prices.total("ignored", 3)); // 24.
~~~

A passing unit test does not prove bean configuration is right; a context starting up cleanly does not prove business logic is right. A clear graph makes it easy to **test both**.

## 12. Misconceptions to Avoid

1. **Is a bean graph the same as a call graph?** No. A dependency does not mean a method is called on every execution path.
2. **Does Spring manage every object created with `new`?** No. Only objects/beans registered and managed through appropriate mechanisms.
3. **Is the graph always a DAG?** No. Cycles can be configured; constructor cycles are normally unresolvable.
4. **Is there a single fixed initialization order?** No. Dependencies impose before/after constraints between linked nodes; unrelated nodes have no general order you should rely on.
5. **Does `@DependsOn` replace DI?** No; it enforces init ordering, rather than passing a collaborator as a constructor/factory parameter.
6. **Does `@Order` control all singleton creation order?** No.
7. **Does `@Lazy` remove a dependency?** No; it only affects creation/retrieval timing in applicable cases.
8. **Does a prototype injected into a singleton automatically change instance on every method call?** No.
9. **Does a `@Component` in any package appear automatically in the context?** No, appropriate registration/scanning is required.
10. **Does the Spring IoC container require Spring Boot?** No; this program only uses `spring-context` with Java 17.

## 13. Exercises with Answers

**Exercise 1.** Service A needs B and C; both B and C need D. Draw the graph and state whether B and C share D if D is a singleton.

**Answer:** There are four nodes for bean definitions A, B, C, D and edges A→B, A→C, B→D, C→D. Both B and C can receive **the same singleton bean D** if injection points to the same definition within one context. Do not infer that the whole context contains only four objects, as configuration and infrastructure beans also exist.

**Exercise 2.** A takes B via constructor, B takes C, and C takes A. Should A or C be created first?

**Answer:** No constructor order can resolve the A→B→C→A cycle. You must change the design or dependency contracts, not reorder `@Bean` method names.

**Exercise 3.** The context has two beans implementing `ProductCatalog`; `PriceService` needs one. What does Spring do?

**Answer:** Without a unique selection rule, injection may fail due to ambiguity. Use qualifiers/primary or change bean registration for clarity.

**Exercise 4.** A prototype bean is injected into a singleton. Does each call to the collaborator inside the singleton get a new object?

**Answer:** Not automatically. The singleton normally retains the instance injected at initialization; to get a fresh one per call, use an appropriate provider/lookup.

**Exercise 5.** Does `@DependsOn("bootstrap")` pass the `bootstrap` object into the annotated bean's constructor?

**Answer:** No. It only declares a named initialization constraint (and affects singleton destruction order accordingly), without supplying the object as an argument.

## 14. Application Checklist

- [ ] Identify which nodes are beans and the scope of each bean.
- [ ] Draw edges in the **consumer → dependency** direction.
- [ ] Trace the factory/constructor parameter that creates each edge.
- [ ] Distinguish interface types, bean definitions, object instances, and runtime call graphs.
- [ ] Check for missing/duplicate beans and qualifier/primary rules.
- [ ] Detect constructor cycles and avoid hiding dependencies with service locator calls.
- [ ] Do not rely on declaration order of unrelated beans.
- [ ] Use `@DependsOn` only when a genuine special init-ordering need exists.
- [ ] Check singleton, prototype, lazy/provider, and lifecycle behavior as needed.
- [ ] Run the JDK 17+ example and verify the exact **five stdout lines**.
- [ ] Test behavior with fake dependencies and test wiring with a context.

**In summary:** A dependency graph answers **"which bean needs which bean?"**. Spring Core Container provides mechanisms to **register, select, create, inject, and manage beans**, while clean separation of responsibilities and accurate business logic remain the application designer's job.

### Official Documentation

- [Spring Bean Dependencies](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-collaborators.html)
- [Java Configuration / @Bean](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html)
- [Composing Java-based Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html)
- [Using depends-on](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-dependson.html)
