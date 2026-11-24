# Constructor Injection and Ensuring Valid State — Spring Framework Core Container

## 1. Problem to Solve

Suppose `CheckoutService` needs to calculate the total for an order and record the transaction. It depends on `PricingPolicy` to compute the total amount and `AuditTrail` to log the history. Both are **required dependencies**: if either dependency has not been provided, the service **should not be created successfully only to throw a `NullPointerException` later when a method is called**.

**Constructor injection** is a design in which required dependencies appear as **constructor parameters**; the caller or the Spring container must supply them at object creation time. The constructor can validate them, ensuring the object never escapes in a state missing an essential component.

~~~mermaid
flowchart LR
    Container["Spring IoC Container"] -->|"creates and supplies"| P["pricingPolicy : PricingPolicy"]
    Container -->|"creates and supplies"| A["auditTrail : AuditTrail"]
    P -->|"constructor parameter"| S["checkoutService : CheckoutService"]
    A -->|"constructor parameter"| S
    S -->|"has required collaborators"| Use["checkout(...)"]
~~~

In the diagram, the arrows from the dependencies to the service represent **the flow of objects supplied into the constructor**. If you draw a *dependency graph* using the **consumer → dependency** convention, you write `CheckoutService → PricingPolicy` and `CheckoutService → AuditTrail`. Do not confuse those two arrow conventions.

After this lesson you can:

1. Write constructors accepting required dependencies instead of calling `new` or `ApplicationContext.getBean(...)` from business code.
2. Understand how Spring automatically selects a bean's **single constructor** (`@Autowired` is not required when there is only one constructor).
3. Enforce non-null references and valid configuration values **right at the initialization boundary**, even when the object is constructed manually outside Spring.
4. Use `private final` appropriately and understand its limits regarding immutability and thread safety.
5. Test wiring, constructor guards, business logic, and missing-bean cases.
6. Run a Java 17+ example using **plain Spring Framework Core Container**, Maven, `javac`/`java`, and exact stdout verification.
7. Distinguish constructor injection from setter/field injection, optional dependencies, scope/lazy behavior, and dependency cycles.

**Scope:** this lesson focuses on **constructor injection and post-initialization state validity**, without diving into Spring Boot, MVC, JPA, transactions, or external validation frameworks.

## 2. What Is Dependency Injection Without Spring?

In plain Java, a class might instantiate its collaborator directly:

~~~java
public final class CheckoutService {
    private final PricingPolicy pricing = new PricingPolicy(150);
    // Service decides the price itself; hard to replace with a fake in tests.
}
~~~

**Illustrative snippet**, not a complete Java file; `PricingPolicy` is the business class defined in the section 5 project. Here the service takes on both calculating totals **and choosing/configuring a dependency**.

Designing with constructor injection:

~~~java
public final class CheckoutService {
    private final PricingPolicy pricing;
    private final AuditTrail audit;

    public CheckoutService(PricingPolicy pricing, AuditTrail audit) {
        this.pricing = Objects.requireNonNull(pricing, "pricing is required");
        this.audit = Objects.requireNonNull(audit, "audit is required");
    }
}
~~~

**Illustrative snippet**, requiring `Objects` imports and the two collaborator definitions. Here:

- The class transparently declares that it needs `PricingPolicy` and `AuditTrail` to exist in a valid state.
- The caller **must choose and provide** the dependencies at constructor invocation time.
- There is no default constructor allowing an “empty” `CheckoutService` to be created and forgotten before injection.
- `Objects.requireNonNull` throws `NullPointerException` **inside the constructor** if an argument is null, instead of constructing a broken object.
- `private final` ensures the fields are assigned once across all valid constructor paths; external code cannot arbitrarily overwrite the fields.

Plain Java already supports DI:

~~~java
PricingPolicy pricing = new PricingPolicy(150);
AuditTrail audit = new AuditTrail();
CheckoutService service = new CheckoutService(pricing, audit);
~~~

This is an illustrative snippet of *manual wiring*. Spring did not invent Java constructors; it performs **object graph assembly based on bean definitions** and supplies constructor arguments for the beans it creates.

### Three Distinct Layers

| Layer | Responsibility | Example |
| --- | --- | --- |
| Class contract | Define what is required, enforce invariants | `CheckoutService(PricingPolicy, AuditTrail)` |
| Composition/wiring | Choose the right instances to pass into the constructor | Spring resolves two beans by type |
| Business usage | Invoke methods on an already valid object | `checkout("BOOK", 2)` |

An **invariant** is a condition that must hold true for an object in a valid state. In this example: both dependencies are non-null. In `PricingPolicy`, unit price must be positive. In `checkout(...)`, inputs must be valid before recording an audit entry. *Constructor invariant* checks and *business input validation* do not replace each other.

## 3. Constructors Prevent Half-Initialized State

Compare with field/setter injection for required dependencies:

~~~java
class UnsafeCheckoutService {
    private PricingPolicy pricing;
    private AuditTrail audit;

    void setPricing(PricingPolicy pricing) {
        this.pricing = pricing;
    }

    void setAudit(AuditTrail audit) {
        this.audit = audit;
    }
}
~~~

**Illustrative code**, not a runnable file. With such an API, a caller can create an instance and call only one setter or none at all. Before configuration completes, the object already exists yet **does not satisfy its invariants**.

Constructor injection makes it impossible to create an instance through **that public constructor** without the required parameters. When the Spring container creates a bean, it must locate the constructor dependencies, instantiate or fetch the matching beans, and pass them in **before returning the initialized bean** to consumers under the normal lifecycle.

| Characteristic | Constructor injection | Setter injection | Field injection |
| --- | --- | --- | --- |
| Required dependencies visible in API | Yes, in constructor | Usually not | Not in constructor signature |
| Can instantiate service in plain Java for unit tests | Easy | Requires calling setters | Requires framework/reflection or extra API |
| Can use `final` for references | Natural | Usually not | Not feasible with standard field injection |
| Enforces valid state from end of constructor | Yes, via validation | Needs additional mechanism | Depends on container lifecycle/injection |
| Suitable for truly optional post-creation values | Possible, though usually not primary goal | Better fit in some designs | Less transparent |

**Avoid dogmatism:** setter injection has its place for *genuinely optional* dependencies or objects needing reconfiguration. A class might need multiple injection styles due to third-party library APIs. Still, for required business collaborators, constructor injection is typically the most testable and maintainable default.

### Common Pitfall: Assuming `final` Makes an Object Automatically Immutable

The field:

~~~java
private final AuditTrail audit;
~~~

only guarantees that **the `audit` reference cannot be reassigned** after initialization. If `AuditTrail` holds a mutable list, its methods can still alter that list's contents. Therefore:

- A `final reference` does not imply *deep immutability*.
- A singleton bean called by multiple threads must still ensure **thread safety** for mutable state.
- Do not expose a mutable list via a getter and assume the service is immutable.
- Constructor validation does not guarantee every subsequent method call will succeed; it only guarantees **the initial object is valid with respect to checked invariants**.

For instance, use `List.copyOf(...)` when publishing an audit snapshot, avoiding handing an internal list reference to callers to mutate.

## 4. How Does Spring Choose a Constructor?

A Spring-managed bean with **only one constructor** can be written as:

~~~java
@Component
public class OrderService {
    private final PricingPolicy pricing;

    public OrderService(PricingPolicy pricing) {
        this.pricing = Objects.requireNonNull(pricing);
    }
}
~~~

**This is a snippet, not full project code.** Once Spring has registered `OrderService` as a bean and knows an appropriate `PricingPolicy` bean, Spring 4.3+ can automatically use the single constructor **without requiring `@Autowired`** on the constructor.

With multiple constructors or complex candidates, constructor selection rules apply:

~~~java
@Component
public class OtherService {
    private final PricingPolicy pricing;

    public OtherService() {
        throw new IllegalStateException("unsupported configuration");
    }

    @Autowired
    public OtherService(PricingPolicy pricing) {
        this.pricing = Objects.requireNonNull(pricing);
    }
}
~~~

This snippet only illustrates the annotation and constructor selection, not standalone runnable source; in such a setup, mark the intended constructor with `@Autowired` to make selection explicit. Do not add a no-arg constructor just to please Spring and leave the service missing its dependencies.

**Key rules to remember:**

- A class with **one constructor**: that constructor is generally chosen by Spring, even without `@Autowired`.
- Multiple constructors: explicitly identify the constructor for required dependencies; do not expect Spring to guess business intent.
- A constructor marked `@Autowired(required=true)` must be the required choice; do not mark multiple different constructors as required.
- If multiple constructors are marked `@Autowired(required=false)`, Spring selects according to dependency resolution rules; this style can be harder to read than a single clear constructor.
- Spring picks **bean candidates** based on type, qualifiers, primary markers, and matching rules. If a required candidate is missing or ambiguous, bean creation fails.

**Class registration differs from having Java source:** a class annotated with `@Component` does not appear in the context unless discovered by component scanning or registered explicitly. In the runnable example, we call `context.register(AppConfig.class, CheckoutService.class)` directly so we do not depend on scanning an entire package.

## 5. Complete Java 17+ and Spring Core Container Example

The following program demonstrates four things:

1. Spring can instantiate `CheckoutService` **via its single constructor without `@Autowired`**.
2. The container supplies the exact **two required beans** that were registered.
3. After initialization, the service can execute business logic and holds **the exact references** managed by the context.
4. If constructed in plain Java with a null dependency or invalid price, the constructor **fails fast** immediately.

Uses **JDK 17+**, Maven, and **Spring Framework 6.2.19** via the `spring-context` module. The version is pinned for reproducibility, not claimed as the latest. No Spring Boot or HTTP server needed.

Directory layout:

~~~text
constructor-di-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ConstructorInjectionDemo.java
~~~

### 5.1. `pom.xml` File

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>constructor-di-demo</artifactId>
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
                    <mainClass>demo.ConstructorInjectionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Maven downloads `spring-context` and its related transitive dependencies. To run `javac` manually, you must place the Spring JAR and full dependencies on the classpath; do not put only a single `spring-context.jar` and expect the compiler/runtime to have all modules.

### 5.2. `src/main/java/demo/ConstructorInjectionDemo.java` File

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Component;

public final class ConstructorInjectionDemo {
    private ConstructorInjectionDemo() {}

    public static final class PricingPolicy {
        private final int unitPrice;

        public PricingPolicy(int unitPrice) {
            if (unitPrice <= 0) {
                throw new IllegalArgumentException("unitPrice must be positive");
            }
            this.unitPrice = unitPrice;
        }

        public int total(int quantity) {
            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }
            return Math.multiplyExact(unitPrice, quantity);
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

    @Component("checkoutService")
    public static final class CheckoutService {
        private final PricingPolicy pricing;
        private final AuditTrail audit;

        // Single constructor: @Autowired is not required.
        public CheckoutService(PricingPolicy pricing, AuditTrail audit) {
            this.pricing = Objects.requireNonNull(
                    pricing, "pricing is required");
            this.audit = Objects.requireNonNull(
                    audit, "audit is required");
        }

        public PricingPolicy pricing() {
            return pricing;
        }

        public AuditTrail audit() {
            return audit;
        }

        public String checkout(String sku, int quantity) {
            if (!"BOOK".equals(sku)) {
                throw new IllegalArgumentException("unknown sku");
            }
            String receipt = sku + " x " + quantity
                    + " = " + pricing.total(quantity);
            audit.record(receipt);
            return receipt;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public PricingPolicy pricingPolicy() {
            return new PricingPolicy(150);
        }

        @Bean
        public AuditTrail auditTrail() {
            return new AuditTrail();
        }
    }

    private static void runWithSpring() {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext()) {
            // Register directly; no component scan needed.
            context.register(AppConfig.class, CheckoutService.class);
            context.refresh();

            CheckoutService service =
                    context.getBean(CheckoutService.class);
            PricingPolicy pricing = context.getBean(PricingPolicy.class);
            AuditTrail audit = context.getBean(AuditTrail.class);

            System.out.println("registered=" +
                    context.containsBean("checkoutService"));
            System.out.println("pricingInjected=" +
                    (service.pricing() == pricing));
            System.out.println("auditInjected=" +
                    (service.audit() == audit));
            System.out.println("serviceSingleton=" +
                    (service == context.getBean(CheckoutService.class)));
            System.out.println("receipt=" + service.checkout("BOOK", 2));
            System.out.println("audit=" + audit.snapshot());
        }
    }

    private static void checkConstructorGuards() {
        try {
            new CheckoutService(null, new AuditTrail());
            System.out.println("nullGuard=UNEXPECTED");
        } catch (NullPointerException failure) {
            System.out.println("nullGuard=" + failure.getMessage());
        }

        try {
            new PricingPolicy(0);
            System.out.println("invalidPrice=UNEXPECTED");
        } catch (IllegalArgumentException failure) {
            System.out.println("invalidPrice=" + failure.getMessage());
        }
    }

    public static void main(String[] args) {
        runWithSpring();
        checkConstructorGuards();
    }
}
~~~

**Notable Java/Spring points:**

- `CheckoutService` is annotated with `@Component("checkoutService")` and registered **directly** via `context.register(..., CheckoutService.class)`. No `@ComponentScan` or `@Autowired` is needed.
- `CheckoutService` has **one public constructor** taking `PricingPolicy` and `AuditTrail`. Spring locates the two registered beans and supplies them when creating the service.
- The two dependencies are provided by two `@Bean` factory methods in `AppConfig`. They are solely responsible for creating collaborators; the service never queries the bean factory itself.
- `Objects.requireNonNull(...)` guards the constructor even when a caller creates the service via `new` outside Spring and passes null.
- `PricingPolicy(150)` is valid; `PricingPolicy(0)` throws an exception at initialization, never producing an invalid pricing policy.
- `Math.multiplyExact` raises an error if integer multiplication overflows instead of silently returning a wrong number; `quantity <= 0` is blocked.
- `AuditTrail.snapshot()` returns a read-only copy of recorded events. The example uses a simple list because it runs on a single thread, **without claiming this mutable bean is thread-safe**.
- The context is closed upon exiting `try-with-resources`. The lesson does not rely on creation order for beans lacking dependency edges or on Spring-generated class names.

### 5.3. Running with Maven

From the `constructor-di-demo` directory:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

**Exact 8 stdout lines printed by the Java program itself across the happy path + constructor checks:**

~~~text
registered=true
pricingInjected=true
auditInjected=true
serviceSingleton=true
receipt=BOOK x 2 = 300
audit=[BOOK x 2 = 300]
nullGuard=pricing is required
invalidPrice=unitPrice must be positive
~~~

The JDK/Maven version output and any logs from Maven/Spring are not part of **the program's eight stdout lines**. The `nullGuard=...` and `invalidPrice=...` lines are not thrown by Spring: they demonstrate **Java code constructor validation** even without a container.

### 5.4. Compiling Manually with `javac` and Running `java`

Because the code imports Spring, `javac` needs a compile classpath and `java` needs a runtime classpath containing Spring dependencies. From the project directory:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

Linux/macOS (bash or zsh):

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -cp "$(cat classpath.txt)" \
  -d out src/main/java/demo/ConstructorInjectionDemo.java
java -cp "out:$(cat classpath.txt)" demo.ConstructorInjectionDemo
~~~

Windows PowerShell:

~~~powershell
$deps = (Get-Content -Raw classpath.txt).Trim()
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -cp "$deps" -d out src/main/java/demo/ConstructorInjectionDemo.java
java -cp "out;$deps" demo.ConstructorInjectionDemo
~~~

The classpath separator is `:` on Unix and `;` on Windows. Both ways invoke the same `main` with the same eight application stdout lines. If the compiler reports missing package `org.springframework...`, check Maven/classpath; the program has not even reached Spring DI yet.

## 6. How Do We Verify Constructor Injection Worked Correctly?

| Output | Evidence | What Does It Not Prove? |
| --- | --- | --- |
| `registered=true` | The bean is known to Spring under the name `checkoutService` | Does not prove all business paths are correct |
| `pricingInjected=true` | Service holds the exact `PricingPolicy` bean returned by context | Does not guarantee all price calculations are valid |
| `auditInjected=true` | Service holds the exact `AuditTrail` bean in the context | Does not guarantee AuditTrail is thread-safe |
| `serviceSingleton=true` | Service has one instance per bean definition in this context | Does not mean a JVM-wide singleton |
| `receipt=BOOK x 2 = 300` | Price 150 times quantity 2; checkout contract works | Not a test of all products/SKUs |
| `audit=[BOOK x 2 = 300]` | Audit was recorded after a successful checkout call | Does not guarantee durable persistence |
| `nullGuard=pricing is required` | Constructor rejects a null collaborator | Does not verify Spring behavior when a bean is missing |
| `invalidPrice=unitPrice must be positive` | PricingPolicy constructor rejects a 0 price config | No invalid-object bean was created by this test case |

In the illustrative configuration, `AppConfig` has exactly one `PricingPolicy` bean and one `AuditTrail` bean. Thus, injection by type is unambiguous. In a real project, if multiple beans share the same type, specify the candidate with qualifiers/primary or fix the configuration instead of guessing Spring will pick by declaration order.

**Read the two distinct checks carefully:** ensuring created objects are **non-null** via constructor guards is one requirement; ensuring the object is **the intended bean** is another requirement. The identity checks in the example show wiring of two singleton collaborators within the same context, not a rule for every scope.

## 7. Fail Fast When Dependencies Are Missing or Configuration Is Invalid

### 7.1. Missing Required Bean

If `CheckoutService` is registered but the context has no compatible `AuditTrail` bean, Spring **cannot complete the service's constructor**. With a non-lazy singleton (the default), the problem is typically detected during `context.refresh()`; the error chain normally shows `UnsatisfiedDependencyException` or an underlying `NoSuchBeanDefinitionException`.

**Illustrative** negative test example, not a standalone Java file:

~~~java
try (AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext()) {
    context.register(CheckoutService.class); // Missing PricingPolicy and AuditTrail
    context.refresh(); // Expected to fail while creating the required bean.
}
~~~

With `@Lazy` or another scope, the failure may be deferred until Spring actually creates the bean. **Do not conclude that because the context reported no error, every dependency across all scopes was verified successfully.**

**Do not use `@Autowired(required=false)` or `Optional<T>` merely to hide a missing required dependency.** A service lacking a pricing policy cannot process orders properly; starting up with a null or bogus default value is an invalid design.

### 7.2. Dependency Exists but Has Invalid State

Suppose a factory declares:

~~~java
@Bean
PricingPolicy pricingPolicy() {
    return new PricingPolicy(0);
}
~~~

This snippet illustrates **replacing** the factory in the demo's `AppConfig`, not placing two methods with the same name side by side. The context has a bean definition, yet when the factory runs, `new PricingPolicy(0)` throws `IllegalArgumentException`. Spring may wrap it in a `BeanCreationException` for the bean being created.

**Two different kinds of fail-fast:**

- **Missing dependency:** the container cannot resolve enough beans to invoke the service constructor.
- **Invalid dependency:** a bean/factory was selected, but the constructor/factory itself rejects invalid values.

Both are better than letting a half-valid object serve requests. Still, failing fast depends on *when* the bean is created (eager/lazy/prototype).

### 7.3. Two Dependencies of the Same Type with Ambiguous Selection

If `primaryPricingPolicy` and `secondaryPricingPolicy` both have type `PricingPolicy`, single-value injection becomes ambiguous:

~~~java
public CheckoutService(
        @Qualifier("primaryPricingPolicy") PricingPolicy pricing,
        AuditTrail audit) {
    this.pricing = Objects.requireNonNull(pricing);
    this.audit = Objects.requireNonNull(audit);
}
~~~

**Illustrative snippet only**; requires importing `org.springframework.beans.factory.annotation.Qualifier`, having the matching beans, and placing it inside an appropriate class. Spring supports placing qualifiers on constructor parameters; when many candidates exist, state the selection policy explicitly rather than relying on an accidental parameter name match.

`@Primary` fits when you want a default bean; a collection or provider fits when business logic needs multiple instances, not when only a single policy is allowed.

## 8. Constructor Dependency Cycles: Why Neither Object Can Be Created First

Example:

~~~java
final class Alpha {
    Alpha(Beta beta) {}
}
final class Beta {
    Beta(Alpha alpha) {}
}
~~~

This snippet shows two mutually dependent classes, without Spring registration yet. If Spring is asked to instantiate both as managed beans via required constructors, the graph has a cycle:

~~~mermaid
flowchart LR
    A["Alpha"] --> B["Beta"]
    B --> A
~~~

To create Alpha it needs Beta, and to create Beta it needs Alpha, yet neither has finished being created. Spring typically reports an error involving `BeanCurrentlyInCreationException` or another exception wrapper.

**Do not fix this by converting every constructor to field injection to let Spring “break the cycle”**, as the result can be partially initialized objects and hard-to-control ownership relationships. Rebalance responsibilities instead: extract a shared service, use events, or introduce an abstraction that eliminates the mandatory cycle at construction time.

Certain setter-based cycles can be resolved by Spring under specific conditions; that **is not a safety guarantee for every cycle** and does not make constructor cycles valid.

## 9. Configuration Values Must Also Be Validated at the Boundary

Constructor injection does not apply only to interface collaborators. A configuration bean like `PricingPolicy` also needs **valid data**.

Example:

~~~java
public PricingPolicy(int unitPrice) {
    if (unitPrice <= 0) {
        throw new IllegalArgumentException("unitPrice must be positive");
    }
    this.unitPrice = unitPrice;
}
~~~

Whether `unitPrice` comes from a literal, `Environment.getRequiredProperty(...)`, `@Value`, or another configuration mechanism, the constructor must still protect invariants wherever possible. The container can resolve and convert a value, but **it does not inherently understand every business rule**, such as requiring positive prices or maximum retry counts.

Sensible design steps:

1. **Declare invariants:** positive unit price, valid currency code, non-null dependencies.
2. **Resolve data:** fetch the property/bean from the right source, with the right name and type.
3. **Validate in constructor/factory:** never store invalid state.
4. **Test negative paths:** missing bean, manually passed null, invalid value, ambiguity.
5. **Allow meaningful bootstrap failures:** do not catch and substitute a wrong business fallback to mask misconfiguration.

If a dependency needs valid configuration changes over its lifecycle, choose an immutable value object design or a controlled update policy. Constructor validation only acts **at initialization time**; it does not prevent a mutable collaborator from being corrupted later.

## 10. Constructor Injection with Interfaces and Unit Testing

A major advantage of constructor DI is testing without Spring. Contract example:

~~~java
interface PriceLookup {
    int unitPrice(String sku);
}

final class OrderCalculator {
    private final PriceLookup lookup;

    OrderCalculator(PriceLookup lookup) {
        this.lookup = Objects.requireNonNull(lookup);
    }

    int total(String sku, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity");
        }
        return Math.multiplyExact(lookup.unitPrice(sku), quantity);
    }
}
~~~

These classes are a Java snippet that can live in a suitable file/test; **not a standalone program with `main`**. In a unit test, inject a fake lambda:

~~~java
PriceLookup fake = sku -> 25;
OrderCalculator calculator = new OrderCalculator(fake);
System.out.println(calculator.total("ANY", 3)); // 75
~~~

You can test null guards, inputs, overflow, and behavior without loading the Spring framework. That stands in sharp contrast to a service querying the container via the **service locator pattern**:

~~~java
// Illustrative anti-pattern:
PricingPolicy pricing = applicationContext.getBean(PricingPolicy.class);
~~~

If every business method pulls beans that way, the dependency list is hidden from the constructor, tests require mocking the container or complex setup, and runtime errors can surface late.

**Not every collaborator has to be an interface.** When there is only one stable implementation or a value object, a constructor accepting a concrete class is completely valid. Interfaces shine when there are multiple strategies, when separating domain from infrastructure, or when faking in unit tests.

## 11. When a Constructor Has Many Dependencies

Constructor injection makes required dependencies explicit in the API. If a signature contains 12–15 collaborators, inspect **the class's responsibilities and reasons to change**, rather than treating a specific parameter count as an automatic flaw. An orchestrator coordinating multiple related steps can still be reasonable.

Do not shorten the signature by hiding collaborators inside `ApplicationContext`, field injection, or a giant `Dependencies` bag: the underlying complexity still exists. Group methods by the business capabilities they use, then consider splitting loosely related responsibilities; group fields into a value object only when those values share meaning and invariants. Any split must be verified so execution order and side effects are not altered.

## 12. Scope, Lazy Initialization, and Valid State

| Case | Key Point to Remember |
| --- | --- |
| Non-lazy singleton (default) | Typically instantiated during `ApplicationContext.refresh()`; missing dependencies usually fail early |
| `@Lazy` singleton | May be created on first request; constructor errors can appear late |
| Prototype | Each bean request typically runs a new constructor and checks its own invariants |
| Prototype injected directly into singleton | Dependency is normally resolved once when the singleton is created, not re-created on every method call |
| Scoped proxy/provider | May affect injection timing/object identity; does not mean constructor guards automatically inspect the final target on every request |
| Manually instantiated with `new` | Spring does not intervene, yet the Java constructor guards themselves still run |
| Closed context | Do not create or retrieve further managed dependencies from a shut-down context |

**Do not equate “Spring injected a non-null reference” with “every remote/database operation is guaranteed to succeed”.** A collaborator can be non-null while an external connection fails later. Constructors enforce invariants that are **feasible and stable** at creation time; business/external failures still must be handled at the appropriate responsibility layer.

A singleton bean holding mutable state across multiple threads must be designed to be thread-safe; `final` on a field only prevents reassigning the reference, not concurrent mutation of the underlying object.

## 13. Common Errors and Fixes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `UnsatisfiedDependencyException` at startup | Constructor needs a bean with no matching candidate | Check `@Bean`, component registration/scan, type, and qualifiers |
| `NoSuchBeanDefinitionException` | Spring lacks a bean for the required name/type | Register the collaborator, verify loaded configuration |
| `NoUniqueBeanDefinitionException` | Multiple candidate beans for a single-value parameter | Use `@Qualifier`, `@Primary`, or refine the business selection |
| `BeanCurrentlyInCreationException` | Dependency cycle across constructors/factories | Sketch the graph, split responsibilities; do not mask cycles with field injection |
| Service created with `new` outside Spring has null dependency | Caller bypassed container without honoring contract | Constructor `requireNonNull`, proper manual wiring, or fetch bean from context |
| Bean factory creates object with 0/negative price | Invalid configuration value for required setting | Validate in `PricingPolicy` constructor; fail fast |
| `@Autowired` on multiple required constructors | Spring cannot tell which constructor is required | Keep one clear constructor, or declare per supported selection rules |
| Too many constructor arguments | Service may hold too many responsibilities | Refactor class boundaries instead of hiding arguments behind setters |
| Wanted `final`, so used direct field injection | Field injection does not fit final constructor assignment | Prefer constructor injection |
| Multiple threads modify shared singleton AuditTrail | Mutable list is not automatically thread-safe | Synchronization, suitable concurrent collection, or stateless design |
| Unit test must boot all of Spring to instantiate one service | Service depends on container/service locator | Pass collaborators via constructor; test with fakes |
| Context starts cleanly yet service fails on another request | Only tested one input; remote calls/logic can still fail | Separate wiring tests from business/edge-case tests |
| Error appears only on first `getBean` call | Lazy/prototype bean delays instantiation | Check creation timing, not only context startup status |
| Added default constructor creating service without dependencies | Allows object to exist in an invalid state | Remove the meaningless constructor, require dependencies via constructor |

**Debugging workflow:** identify the bean being created, inspect its constructor parameter list, check all candidates of that type, and follow the `Caused by` chain to the root error. If it is an `IllegalArgumentException` from a constructor, check configured values; if it is a missing or ambiguous bean, fix registration/qualifiers. Never catch `BeansException` at bootstrap and let the application run with null dependencies.

## 14. Testing at Two Levels

**Unit tests (without Spring):** instantiate `PricingPolicy`, `AuditTrail`, and `CheckoutService` in plain Java; verify:

- `new CheckoutService(null, audit)` is rejected immediately.
- `new CheckoutService(pricing, null)` is rejected immediately.
- `new PricingPolicy(0)` is rejected.
- `checkout("BOOK", 2)` returns the right receipt and appends exactly one audit event.
- `checkout("BOOK", 0)` is rejected; no audit entry is recorded.
- `checkout("UNKNOWN", 1)` is rejected per the SKU contract.

**Spring wiring test:** create a context with `AppConfig` and `CheckoutService.class`, and verify:

~~~java
try (AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext()) {
    context.register(AppConfig.class, CheckoutService.class);
    context.refresh();

    CheckoutService service = context.getBean(CheckoutService.class);
    PricingPolicy pricing = context.getBean(PricingPolicy.class);
    if (service.pricing() != pricing) {
        throw new IllegalStateException("unexpected pricing bean");
    }
}
~~~

This is **a snippet drawn from the demo class context**, not a standalone file. It proves *wiring*, not every business case on its own.

**Negative Spring integration test:** use a configuration intentionally missing `AuditTrail` or defining two `PricingPolicy` beans of the same type without clear selection. Verify the error type/cause without locking the test to the exact verbatim stack trace, as messages can change across Spring/JDK versions.

**Do not rely on Java's default `assert` for mandatory checks**, because assertions can be disabled if the JVM runs without `-ea`. Use test framework assertions or explicit checks that throw exceptions.

## 15. Practice Exercises with Answers

**Exercise 1 — Valid initialization.** A service has constructor `S(A a, B b)` and no other constructors. If A exists but B is not registered, can Spring return an `S` with `B=null`?

**Answer:** For a required dependency under normal constructor resolution rules, Spring must resolve B; if missing, bean creation fails rather than silently instantiating a service with `B=null`.

**Exercise 2 — `@Autowired`.** A Spring bean has only one public constructor taking two collaborators. Is `@Autowired` required?

**Answer:** Not required since Spring Framework 4.3; the container can select the single constructor. You still must ensure the bean is registered and its dependencies resolve.

**Exercise 3 — Object outside Spring.** Someone calls `new CheckoutService(null, new AuditTrail())`. Does Spring intercept it first?

**Answer:** Spring is not involved in this `new` call. However, `Objects.requireNonNull(pricing)` inside the constructor throws the exception; the class invariant does not depend on the container.

**Exercise 4 — `final`.** Does `private final AuditTrail audit` make AuditTrail's internal list immutable and thread-safe?

**Answer:** No. It only keeps the reference unchanged; `AuditTrail`'s state can still be mutable. Separate state-protection design is required.

**Exercise 5 — Invalid config.** When is `PricingPolicy(0)` rejected?

**Answer:** Right inside the `PricingPolicy` constructor. If Spring creates the bean from a factory returning `new PricingPolicy(0)`, the failure is typically wrapped in a bean creation exception.

**Exercise 6 — Dependency cycle.** A's constructor needs B, and B's constructor needs A. Can simply reordering bean definitions allow startup?

**Answer:** No. This is a mandatory cycle A→B→A, and no complete object creation order can resolve it; the design must be fixed.

**Exercise 7 — Multiple candidates.** The context has two `PricingPolicy` beans. Is the single parameter `PricingPolicy pricing` in the constructor enough for Spring to know which to pick?

**Answer:** Not necessarily; Spring also checks qualifiers, `@Primary`, and other resolution rules. When truly ambiguous, specify the choice explicitly or fix the configuration.

**Exercise 8 — Valid state.** The constructor already checked that all references are non-null. Does that mean every `checkout` call will succeed?

**Answer:** No. The method still validates SKU and quantity and may encounter overflow or business exceptions. Constructor valid state and method input validation are two different layers.

## 16. Application Checklist

- [ ] List **required** dependencies and place them in a public constructor.
- [ ] Avoid having services call `new` or `getBean(...)` for dependencies outside the composition root.
- [ ] Store required references in `private final` fields where appropriate.
- [ ] Use `Objects.requireNonNull`/explicit validation for invariants, not relying solely on Spring.
- [ ] Do not add a default constructor that leaves the object missing dependencies.
- [ ] For a single constructor, understand why `@Autowired` is optional.
- [ ] With multiple constructors, explicitly mark the chosen constructor and required semantics.
- [ ] Verify the class is registered as a bean; annotations in source do not register beans by themselves.
- [ ] Resolve candidates via type/qualifier/primary instead of relying on chance.
- [ ] Avoid dependency cycles and constructors with too many responsibilities.
- [ ] Distinguish `final` references from mutable objects and thread safety.
- [ ] Distinguish missing-bean errors from constructors rejecting invalid configuration values.
- [ ] Check lazy/prototype behavior if errors do not appear right at startup.
- [ ] Run Java 17+ and verify the **exact eight stdout lines**.
- [ ] For `javac`/`java`, include the complete Spring classpath.
- [ ] Separately test constructor invariants, business behavior, and Spring wiring.

**Takeaway:** Constructor injection is not merely a way to “pass bean A into bean B”; it is also an **initialization contract**. When required dependencies are declared in the constructor and validated at that same boundary, an object never escapes in a state missing essential collaborators. Spring Core Container handles **resolving and supplying registered dependencies**, while **invariant design and validation** remain guaranteed by Java code.

### Official Documentation

- [Spring Framework 6.2 — Dependency Injection](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-collaborators.html)
- [Spring Framework — Using @Autowired](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [Spring Framework — Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html)
- [AnnotationConfigApplicationContext API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/AnnotationConfigApplicationContext.html)
