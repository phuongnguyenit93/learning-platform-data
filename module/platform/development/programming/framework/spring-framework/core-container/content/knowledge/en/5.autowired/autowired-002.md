# A Class with a Single Constructor Does Not Need `@Autowired`

## 1. Spring's Core Rule

In modern Spring Framework (since **Spring Framework 4.3**), when a class is managed by Spring as a **bean** and that class has only **one constructor**, Spring can select that constructor to instantiate the bean and automatically resolve its dependency parameters. **There is no need to place `@Autowired` on a single constructor.**

Example:

~~~java
public final class OrderService {
    private final PriceCalculator calculator;

    public OrderService(PriceCalculator calculator) {
        this.calculator = calculator;
    }
}
~~~

The snippet above is illustrative only: `PriceCalculator` needs to be defined and registered in the context. Spring can see the `OrderService(PriceCalculator)` constructor, find a matching `PriceCalculator` bean, and invoke the constructor. If all parameters are satisfied, `OrderService` is created without needing `@Autowired`.

**The most important condition:** `OrderService` must actually be **registered for the container to create/manage**. Having exactly one constructor does not automatically make a class appear in the Spring ApplicationContext.

~~~text
Java class has exactly one constructor
            |
            +-- Object created by Spring via bean definition
            |       |
            |       +-- Spring selects the single constructor
            |       +-- Spring looks up beans for parameters
            |       +-- Spring invokes constructor
            |       +-- Object becomes a managed bean
            |
            +-- Object created by caller calling new
                    |
                    +-- Java simply invokes the constructor with the arguments
                        that the caller themselves passed
                    +-- No automatic bean lookup / autowiring
~~~

This rule makes constructor injection code **cleaner**, without changing the nature of Dependency Injection: the service declares its dependencies and receives implementations from the outside.

## 2. Distinguish "Having One Constructor" from "Being Registered with Spring"

A normal Java constructor:

~~~java
public CheckoutService(InventoryPort inventory) {
    this.inventory = java.util.Objects.requireNonNull(inventory);
}
~~~

is sufficient to express a **required dependency**. However, the container only processes it when the class is introduced into the bean graph through a valid path.

### Three Common Registration Ways

| Way | How Does Spring Know the Class? | Who Actually Calls the Constructor? |
| --- | --- | --- |
| `@Component` and component scanning | Scans packages and discovers the component | Spring performs bean instantiation |
| `AnnotationConfigApplicationContext.register(MyService.class)` | Code explicitly registers the bean class | Spring performs bean instantiation |
| `@Bean MyService service(Dependency d) { return new MyService(d); }` | A factory method provides the object | The `@Bean` body itself calls the constructor; factory parameters are injected by Spring |

**Note on the `@Bean` row:** if factory method code writes `return new MyService(d);`, Spring does not automatically "select `MyService`'s constructor" at that step. Spring resolves the **parameters of the factory method** `service(Dependency d)`; the Java method itself calls `new MyService(d)`. This is still DI, but it is not a direct example demonstrating the bean class's single-constructor selection rule.

**`@Component` is not mandatory:** a class can remain completely pure Java if it is explicitly registered with `register(...)`, or if the instance is created via `@Bean`.

### Component Scanning Example

~~~java
@Component
public class ReportService {
    private final ReportRepository repository;

    public ReportService(ReportRepository repository) {
        this.repository = repository;
    }
}
~~~

This is an **illustrative snippet**, not standalone runnable because it also requires importing `Component`, defining `ReportRepository`, and enabling component scanning. When the container discovers `ReportService`, its single constructor is used for injection without requiring the `@Autowired` annotation. If there is no `ReportRepository` bean, bean creation will fail.

### Direct Class Registration Example

~~~java
AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext();

context.register(AppConfig.class, ReportService.class);
context.refresh();
ReportService service = context.getBean(ReportService.class);
context.close();
~~~

This is also **illustrative code**: the classes and appropriate Spring imports must be declared. In the runnable application in section 5, we use this exact registration approach to avoid any confusion with the `@Bean` mechanism creating the service.

## 3. Why Does Constructor Injection Suit Required Dependencies?

Compared to field injection or setter injection, constructors bring clear design benefits:

- **Dependencies appear directly in the class's public API:** just reading the constructor shows what collaborators the service needs.
- **Fail fast:** missing a needed dependency prevents Spring from creating the bean; in plain Java, code is forced to supply the argument.
- **Allows `final` fields:** required references are assigned once at object creation and cannot be reassigned via ordinary setters.
- **Simple plain Java tests:** create fake implementations and pass them into the constructor without starting Spring.
- **No need for the service to hold ApplicationContext:** business classes do not have to look up beans themselves.
- **Easy reuse:** business classes do not need to import Spring if there are no other Spring annotations/dependencies.

Example:

~~~java
public final class CheckoutService {
    private final InventoryPort inventory;
    private final ReceiptPort receipts;

    public CheckoutService(InventoryPort inventory, ReceiptPort receipts) {
        this.inventory = java.util.Objects.requireNonNull(inventory);
        this.receipts = java.util.Objects.requireNonNull(receipts);
    }
}
~~~

This is an **illustrative design snippet**. It has one constructor with **two parameters**. The rule "one constructor does not need `@Autowired`" still applies: it does not limit the constructor to only having **one parameter**. Spring can resolve each parameter by type and matching qualifiers.

**`final` does not mean all collaborators automatically become immutable or thread-safe.** It only guarantees the field reference is not reassigned after the constructor finishes. A singleton bean holding mutable state still requires proper concurrency design.

## 4. Do Not Confuse Three Different "One" Concepts

| Phrase | Meaning | True or False? |
| --- | --- | --- |
| **One constructor** | The class declares exactly one constructor for Spring to consider | This is the condition for the rule not needing `@Autowired` |
| One parameter | The constructor accepts exactly one argument | Not required; it can accept multiple arguments |
| One bean in the context | Only one instance or one corresponding bean definition | Not synonymous; scope/dependency candidates are separate matters |

A class with a single constructor containing three arguments still falls under the rule:

~~~java
public BillingService(AccountRepository accounts,
                      ExchangeRateClient rates,
                      ReceiptSender receipts) {
    this.accounts = accounts;
    this.rates = rates;
    this.receipts = receipts;
}
~~~

This illustrative snippet needs matching fields and interfaces if you want to compile it. Spring must have a **way to resolve each dependency**; merely having one constructor **does not exempt from missing-bean errors**.

A class declaring no explicit constructor has a **default no-arg constructor** provided by Java (when eligible). If such a class is instantiated as a Spring bean, it can be created without constructor arguments. However, this **does not demonstrate injection**: no dependencies are injected into a no-arg constructor.

## 5. Runnable Maven/Spring Framework 6.2, Java 17 Example

The console application directly proves:

1. `OrderService` has **one parameterized constructor**, **no `@Autowired`**, and **no `@Component`**.
2. `PricePolicy` has one implementation registered via `@Bean`.
3. `context.register(AppConfig.class, OrderService.class)` makes Spring aware of the service class.
4. Spring automatically supplies the `PricePolicy` bean to `OrderService`'s constructor.
5. `getBean(OrderService.class)` retrieves the working service, and two singleton lookups return the same reference.

### 5.1. Requirements and Directory Structure

Requires JDK 17+ and Apache Maven. The example uses Spring Framework **6.2.0** via `spring-context`, without Spring Boot, a web server, or a database.

~~~text
one-constructor-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── SingleConstructorDemo.java
~~~

Create `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>one-constructor-demo</artifactId>
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
                    <mainClass>demo.SingleConstructorDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.2. Complete Java File

Save the file `src/main/java/demo/SingleConstructorDemo.java`:

~~~java
package demo;

import java.util.Objects;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class SingleConstructorDemo {
    private SingleConstructorDemo() {}

    // A Java contract: does not depend on Spring.
    public interface PricePolicy {
        int calculate(int unitPrice, int quantity);
    }

    // Implementation selected by configuration.
    public static final class StandardPricePolicy implements PricePolicy {
        @Override
        public int calculate(int unitPrice, int quantity) {
            return Math.multiplyExact(unitPrice, quantity);
        }
    }

    // No @Component and also NO @Autowired.
    // Has only ONE constructor with one required dependency.
    public static final class OrderService {
        private final PricePolicy policy;

        public OrderService(PricePolicy policy) {
            this.policy = Objects.requireNonNull(policy, "policy");
        }

        public String checkout(String sku, int unitPrice, int quantity) {
            Objects.requireNonNull(sku, "sku");
            if (sku.isBlank() || unitPrice < 0 || quantity <= 0) {
                throw new IllegalArgumentException("Invalid order input");
            }
            return sku + "=" + policy.calculate(unitPrice, quantity);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public PricePolicy pricePolicy() {
            return new StandardPricePolicy();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            // Register the service class so Spring directly uses its constructor.
            context.register(AppConfig.class, OrderService.class);
            context.refresh();

            OrderService service = context.getBean(OrderService.class);

            System.out.println("ORDER_BEANS "
                    + context.getBeanNamesForType(OrderService.class).length);
            System.out.println("RESULT "
                    + service.checkout("BOOK", 30, 2));
            System.out.println("SAME_INSTANCE "
                    + (service == context.getBean(OrderService.class)));
        }
    }
}
~~~

### 5.3. Compile and Run with Maven

Inside the `one-constructor-demo` directory:

~~~bash
mvn -version
mvn -q compile exec:java
~~~

The **stdout lines printed by `SingleConstructorDemo` itself**, in order:

~~~text
ORDER_BEANS 1
RESULT BOOK=60
SAME_INSTANCE true
~~~

The `mvn -version` command prints version information. Maven/plugins may print logs or download dependencies on the first run, so **the three lines above do not include all terminal logs**.

### 5.4. Execution Sequence Explained

1. `new AnnotationConfigApplicationContext()` creates an unrefreshed context.
2. `context.register(AppConfig.class, OrderService.class)` registers **both the configuration** and **the service class**. `OrderService` does not need `@Component` because it was registered directly.
3. `context.refresh()` processes `@Configuration` and `@Bean pricePolicy()`, creating the `PricePolicy` bean; the container also instantiates appropriate non-lazy singletons.
4. When needing to create `OrderService`, Spring recognizes that the class has **only the `OrderService(PricePolicy)` constructor**, even without `@Autowired`.
5. Spring resolves a bean compatible with `PricePolicy` (specifically `StandardPricePolicy` exposed via `@Bean`) and invokes the constructor with that instance.
6. `getBean(OrderService.class)` returns the service that already received its dependency; it **does not invoke a new constructor on each lookup** under the default singleton scope.
7. In this context there is only one `OrderService` bean, so `getBeanNamesForType(...)` has length 1.
8. `checkout("BOOK",30,2)` calls `Math.multiplyExact(30,2)` inside the policy, returning 60 and producing the string `BOOK=60`.
9. Looking up the `OrderService` bean type again in the same context returns the same reference, yielding `SAME_INSTANCE true`.
10. `try-with-resources` closes the context. Appropriate destroy callbacks are handled by Spring for managed beans.

Key takeaway: the absence of Spring annotations on `OrderService` does not prevent constructor injection; **bean registration** is what lets Spring know to create the object.

## 6. Plain Java 17: Constructor Injection Still Works Without Spring

To prove constructor injection is not special Spring syntax, try a **standalone** program using only the JDK.

Create `src/main/java/demo/PlainConstructorDemo.java`:

~~~java
package demo;

import java.util.Objects;

public final class PlainConstructorDemo {
    private PlainConstructorDemo() {}

    @FunctionalInterface
    public interface GreetingPort {
        String hello(String name);
    }

    public static final class GreetingService {
        private final GreetingPort greeting;

        public GreetingService(GreetingPort greeting) {
            this.greeting = Objects.requireNonNull(greeting);
        }

        public String greet(String name) {
            return greeting.hello(name);
        }
    }

    public static void main(String[] args) {
        GreetingPort fake = name -> "Hello " + name;
        GreetingService service = new GreetingService(fake);
        System.out.println(service.greet("Lan"));
    }
}
~~~

From the `one-constructor-demo` directory, compile and run **without Maven/Spring**:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/main/java/demo/PlainConstructorDemo.java
java -cp out demo.PlainConstructorDemo
~~~

**Exact stdout:**

~~~text
Hello Lan
~~~

In the plain Java example, **`main` itself supplies the argument** `fake` to the constructor. The JVM does not automatically find an implementation of `GreetingPort`. When using Spring, the container handles selecting and providing dependencies within the corresponding bean graph.

### Does `@Autowired` Have Any Effect When Calling `new` Directly?

Illustrative example:

~~~java
OrderService service = new OrderService(new StandardPricePolicy());
~~~

This is direct instantiation and manual dependency passing; it is valid if the classes are accessible. However, an object created with `new` outside the container **does not automatically become a Spring-managed bean**, nor does it receive Spring's bean post-processing, lifecycle, or proxies. Not needing `@Autowired` on a single constructor is **Spring's constructor selection rule when creating a bean**, not magic triggered on every `new`.

## 7. When Is Explicit `@Autowired` Needed?

### 7.1. Single Constructor: The Annotation Is Usually Redundant

~~~java
@Component
final class ShippingService {
    private final ShippingRatePolicy rates;

    public ShippingService(ShippingRatePolicy rates) {
        this.rates = rates;
    }
}
~~~

**Illustrative** code, requiring a `ShippingRatePolicy` declaration, importing `Component`, and component scanning. When `ShippingService` is a Spring bean and has exactly one constructor, `@Autowired` does not need to be added to select that constructor.

Writing:

~~~java
@Autowired
public ShippingService(ShippingRatePolicy rates) {
    this.rates = rates;
}
~~~

can be used to **express intent** or maintain consistency across a project, but it **does not change the requirement to have the dependency** in the single-constructor scenario. Do not attach the annotation just thinking Java will fail to run without it.

### 7.2. Multiple Constructors: Must Clarify the Selection Strategy

~~~java
@Component
class MultiConstructorService {
    private final ReportRepository repository;

    public MultiConstructorService() {
        this.repository = null;
    }

    @Autowired
    public MultiConstructorService(ReportRepository repository) {
        this.repository = repository;
    }
}
~~~

This is an **illustrative snippet**, not a standalone program. With multiple constructors, the rule "only one constructor is used implicitly" **no longer applies**. Marking the desired constructor with `@Autowired` tells Spring which constructor to use; if the required dependency is missing, bean creation may fail.

Do not add a no-arg constructor just to "make it easy for Spring to create", especially if it leaves the object missing required fields. A business class should strive to have a **single constructor with all required dependencies** whenever the design permits.

If a class has multiple constructors without annotations, Spring also has rules and capabilities to infer constructors based on bean definition/argument types/version. **Do not assume that Spring unconditionally always picks the longest constructor, the first constructor, or the constructor with "the most satisfiable beans".**

### 7.3. `@Autowired(required = false)` on a Constructor Is Not Like an Optional Field

Some developers add `required=false` to turn a required constructor into an optional one. This is an easily misunderstood idea. With multiple constructors, Spring can treat constructors annotated as non-required as candidates and pick a suitable constructor per resolution rules, but **it does not mean Spring passes `null` into every missing parameter**, nor turns an arbitrary class into valid without dependencies.

If a collaborator is optional, consider **`Optional<T>`**, an appropriate `@Nullable`, `ObjectProvider<T>`, or setter injection with safe defaults/behavior. Do not dilute a mandatory constructor just to hide missing-bean errors.

## 8. Having Exactly One Constructor Can Still Fail

A constructor automatically selected by Spring **does not guarantee bean creation will succeed**. Consider these cases:

### Missing Dependency Bean

If `OrderService` requires `PricePolicy` and `AppConfig` does not register a corresponding implementation, Spring cannot resolve the parameter. In an eager singleton example, the error can surface **immediately at `refresh()`**, typically via `UnsatisfiedDependencyException` with a missing-bean cause.

~~~java
// Illustrative error check: do not add AppConfig to context.
context.register(OrderService.class);
context.refresh(); // May fail due to missing PricePolicy.
~~~

This snippet is only for illustrating the scenario and should not be inserted into the main runnable program if you want to preserve section 5's stdout.

### Multiple Beans of the Same Interface

If there are two `PricePolicy` beans while the injection point requires exactly one and has no disambiguation rule, `NoUniqueBeanDefinitionException` can occur. Solutions are usually `@Primary`, `@Qualifier`, or specifying a clear bean name/type at registration.

Example:

~~~java
public OrderService(@Qualifier("standardPolicy") PricePolicy policy) {
    this.policy = policy;
}
~~~

This is an **illustrative snippet**; it requires importing `org.springframework.beans.factory.annotation.Qualifier` and declaring a bean named `standardPolicy`. The rule that a single constructor does not need `@Autowired` **does not forbid** using `@Qualifier` on a parameter.

### Constructor Throws an Exception Itself

If `Objects.requireNonNull(policy)`, validation logic, or a dependency's constructor throws an error, bean creation still fails. `@Autowired` is not an exception handler and does not self-heal an object graph.

### Circular Dependency via Constructor

A graph like `A(B)` and `B(A)` is a constructor cycle that cannot normally be resolved when both need each other to exist. Removing `@Autowired` does not solve the cycle; responsibilities must be redesigned or intentional deferral mechanisms used when truly appropriate.

### Unregistered Class

Even when the constructor is valid and the `PricePolicy` bean is available, if `OrderService` is not declared with `@Bean`, not component-scanned, and not registered via `register(...)`, `context.getBean(OrderService.class)` can still fail with `NoSuchBeanDefinitionException`.

**Conclusion of this section:** annotations are not a magic key to fix all autowiring errors. You must inspect **registration**, **constructor selection**, **dependency resolution**, and **lifecycle** in order.

## 9. `@Bean` Also Has Constructor Injection, But in a Different Place

Compare the two wiring styles.

### Style A: Spring Instantiates the Bean Class Directly

~~~java
context.register(OrderService.class);
context.refresh();
~~~

When `OrderService` has a single constructor `OrderService(PricePolicy)` and the dependency already exists, the container calls the constructor directly. This is the canonical case for the rule that one constructor does not need `@Autowired`.

### Style B: `@Bean` Factory Method Instantiates the Service Itself

~~~java
@Bean
OrderService orderService(PricePolicy policy) {
    return new OrderService(policy);
}
~~~

Spring resolves `PricePolicy` into the **`orderService` method parameter**. Java code inside the factory **itself** calls the constructor. With this approach, the `OrderService` class can be designed without importing Spring and without needing component scanning.

**Do not confuse them**: both A and B can perform Dependency Injection effectively, yet the way Spring decides to call the constructor differs.

With a `@Bean` method, Spring typically does not need `@Autowired` to automatically resolve factory method parameters; that is the behavior of the bean factory infrastructure.

## 10. Unit Testing Without Spring: Benefit of a Clear Constructor

With a simple business class:

~~~java
public interface PricePolicy {
    int calculate(int unitPrice, int quantity);
}
~~~

and `OrderService(PricePolicy policy)`, tests can pass a fake directly:

~~~java
PricePolicy fake = (unitPrice, quantity) -> 123;
OrderService service = new OrderService(fake);

String actual = service.checkout("BOOK", 30, 2);

if (!"BOOK=123".equals(actual)) {
    throw new AssertionError("Expected BOOK=123 but got " + actual);
}
~~~

These two blocks are **illustrative snippets in the same context as the classes in section 5**, not standalone runnable files. The fake needs no database, HTTP client, or Spring context. What should be asserted is the **result and contract-compliant interaction**, not merely "no exception thrown".

### When Wanting to Test Spring Wiring

An integration test can start `AnnotationConfigApplicationContext` and verify retrieving `OrderService`. Running the context checks:

- The bean class and configuration are registered properly.
- `PricePolicy` has a uniquely selected candidate.
- The single constructor is resolved successfully.
- The bean is fit for use.
- Scope and lifecycle follow the configuration.

There is no need to start the container in **every unit test** of `OrderService`; doing so couples tests to infrastructure that business logic does not require.

## 11. Quick Comparison Table

| Scenario | Is `@Autowired` Needed on the Constructor? | Key Point |
| --- | --- | --- |
| Spring creates a bean class with exactly one constructor | **Not needed** | The constructor is implicitly chosen by Spring |
| Single constructor has 2–4 parameters | **Not needed** | Each parameter still needs to be resolvable |
| Class has `@Component` and is scanned, one constructor | **Not needed** | Scanning must be enabled and cover the package |
| Class registered via `context.register(MyClass.class)`, one constructor | **Not needed** | Container knows the bean definition |
| Object manually `new MyClass(dep)` outside Spring | Unrelated to Spring autowiring | Caller supplies dep directly |
| `@Bean MyClass myClass(Dep dep)` calls `new` itself | Not needed on constructor for factory to work | Factory method is injected by Spring |
| Class has multiple constructors and one must be specified | **Usually should be used** | Prevents ambiguity and picking the wrong constructor |
| Has one constructor but missing dependency bean | Writing the annotation won't fix it | Needs a valid bean definition/candidate |
| Has one constructor but multiple beans of same type | Writing the annotation won't fix it | Needs qualifier/primary/selection rule |
| Needs injection into setter/field instead of constructor | Appropriate annotation or injection metadata | The single-constructor rule only applies to constructors |

## 12. Common Misconceptions When Learning `@Autowired`

| Misconception | Truth |
| --- | --- |
| "Every constructor must be annotated with `@Autowired`." | No; Spring 4.3+ automatically uses a bean's single constructor. |
| "Without `@Autowired`, Java doesn't know how to pass parameters." | Java always requires whoever creates an object to pass arguments; Spring only supplies them automatically when it creates the bean. |
| "Having one constructor makes Spring scan the class automatically." | No; proper bean registration/component scan/`@Bean` is required. |
| "Only one constructor means a no-arg constructor." | No; the single constructor can have multiple parameters. |
| "Omitting `@Autowired` removes the dependency bean requirement." | No; constructor parameters must still be resolved. |
| "`@Autowired` handles both missing beans and ambiguous multiple beans." | No; candidates and configuration must be handled properly. |
| "Class has `@Service` so it is definitely scanned." | Annotation is not enough if scanning does not cover the package/class. |
| "With one constructor, that constructor runs before dependencies are created." | Spring usually has to resolve dependencies in order to call the constructor; dependencies are supplied at invocation time. |
| "No `@Autowired` needed means no DI needed." | It is still DI; only the redundant annotation is omitted. |
| "Constructor injection means all state is immutable." | `final` references and immutability/thread safety are separate concerns. |
| "`new` outside the container will be injected automatically." | No; arguments must be passed manually or a managed bean used. |
| "`@Bean` method arguments are injected thanks to annotations on the product constructor." | Factory method arguments are resolved by the container per `@Bean` infrastructure. |
| "With multiple constructors, Spring always picks the longest constructor." | There is no simple rule that holds true across all configurations. |
| "Adding a default constructor is the fix for broken dependencies." | It can allow the object to exist in a state missing required collaborators. |
| "Marking `@Autowired(required=false)` turns all required dependencies optional." | Constructor candidate resolution is more complex; it does not mean safely injecting null. |

## 13. Exercises and Answers

**Exercise 1.** Class `ReportService` has a single constructor accepting `ReportRepository`, is component-scanned by Spring, and has a repository bean. Is `@Autowired` needed?

**Answer:** No. With Spring 4.3+, Spring can use the single constructor and automatically resolve the repository.

**Exercise 2.** A class has a single constructor with three parameters. Does this rule apply?

**Answer:** Yes. The number of **constructors** is 1; the number of **parameters** can be 3. Each parameter must still have a matching dependency.

**Exercise 3.** A class has one constructor, but no bean is registered and scanning is not enabled. Can `getBean(Class)` find it solely because of the constructor?

**Answer:** No. Spring needs to know the bean definition before creating/looking it up.

**Exercise 4.** A service has no `@Autowired`, but its single required constructor accepts `PricePolicy`, and the context has no `PricePolicy` bean. Will adding the annotation fix it?

**Answer:** No. You need to supply a bean implementation or fix dependency configuration; the missing bean is not caused by omitting the annotation in a single-constructor scenario.

**Exercise 5.** Why does the program print `SAME_INSTANCE true`?

**Answer:** `OrderService` is a singleton bean by default in the same context; two lookups return the same instance. This **does not mean** only one instance exists across the entire JVM.

**Exercise 6.** In the `@Bean OrderService service(PricePolicy p)` example returning `new OrderService(p)`, who provides `p` and who calls the constructor?

**Answer:** Spring resolves `p` when calling the factory method; the **`@Bean` body** invokes the constructor via `new`.

**Exercise 7.** If a no-arg constructor is added to `OrderService`, can all attention to constructor selection be ignored?

**Answer:** No. Now there are multiple constructors, so the single-constructor rule no longer applies. A strategy must be clarified, typically marking the desired constructor with `@Autowired`.

**Exercise 8.** When there is only one constructor, can `@Qualifier` be used on a parameter without `@Autowired` on the constructor?

**Answer:** Yes, when wanting to explicitly specify the bean candidate for a parameter in the constructor selected by Spring. Qualifiers/bean names must be declared matching the actual configuration.

**Exercise 9.** Why is `@Autowired` on fields generally discouraged compared to constructor injection for required dependencies?

**Answer:** Field injection makes dependencies less visible, makes plain Java unit testing harder, and is incompatible with `final` fields. Constructors express required dependencies from the moment the object is created.

**Exercise 10.** If using one constructor with two dependencies yet the class has too many responsibilities, does omitting `@Autowired` make the architecture better?

**Answer:** No. Omitting the annotation only shortens the code. Design quality depends on how responsibilities, contracts, and collaborator lifecycles are separated.

## 14. Checklist for Applying to Projects

- [ ] Verify **the class is actually a Spring-managed bean**: component scan, register, or `@Bean`.
- [ ] Count the **number of constructors** on the bean class, not the number of parameters.
- [ ] If there is only **one constructor**, with Spring Framework 4.3+ `@Autowired` is usually not needed.
- [ ] Put required dependencies into the constructor and validate arguments when necessary.
- [ ] Ensure every parameter has a matching bean candidate in the context.
- [ ] If there are multiple beans of the same type, use qualifier/primary or a clear selection policy.
- [ ] Do not add a no-arg constructor just to mask missing-dependency errors.
- [ ] If there are multiple constructors, design a clear selection strategy instead of guessing.
- [ ] Do not assume `@Component` is automatically scanned when its package is outside the scan configuration.
- [ ] With `@Bean` factory methods, remember Spring injects the factory parameters.
- [ ] Distinguish objects created with `new` from instances managed by Spring.
- [ ] Unit test services with plain Java fakes; integration test Spring wiring separately.
- [ ] Review scope/lifecycle and proxy impacts when expanding to AOP/transactions.
- [ ] Do not treat constructor injection as a guarantee of thread safety or transactional consistency.
- [ ] Check application stdout separately from Maven logs and confirm Java 17 compatibility.

### Spring Reference Documentation

- [Using `@Autowired` — constructor injection](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [Constructor-based Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java/basic-concepts.html)

**Conclusion:** If Spring already knows how to create a bean and the bean class has **exactly one constructor**, that constructor is typically used by Spring even without `@Autowired`. This makes constructor injection concise, keeps required dependencies explicit, and simplifies testing. However, it **does not replace** bean registration, does not automatically resolve candidates when beans are missing or ambiguous, and does not make Java `new` outside the container automatically receive dependencies.