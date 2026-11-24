# `@Bean` Method Parameters Express Dependencies in Spring Java Configuration

## 1. Goal: Putting Dependencies into the Method Signature

In the Spring Core Container, a method annotated with `@Bean` is a **factory method** for registering an object managed by Spring. When the object created by that method needs another bean, you can declare the dependency directly using **method parameters** instead of looking up the bean from `ApplicationContext` or calling another `@Bean` method.

Simple example:

```java
@Configuration(proxyBeanMethods = false)
class AppConfig {

    @Bean
    Repository repository() {
        return new InMemoryRepository();
    }

    @Bean
    OrderService orderService(Repository repository) {
        return new OrderService(repository);
    }
}
```

This is an **illustrative** snippet (`Repository`, `InMemoryRepository`, `OrderService`, and imports must be declared separately). When creating the `orderService` bean, Spring resolves the `Repository repository` parameter from the container and passes the instance into the factory method. The configuration author does not have to call `repository()` or `context.getBean(...)`.

The signature `orderService(Repository repository)` makes three things clear:

1. Creating `OrderService` requires a dependency of type `Repository`.
2. The dependency is **resolved by Spring** according to type and the relevant autowiring rules.
3. The factory method receives the resolved dependency and then runs plain Java code: `new OrderService(repository)`.

This separates **declaring dependency relationships** from **object construction logic**, benefiting testing, refactoring, and using `@Configuration(proxyBeanMethods = false)`.

Learning objectives of this lesson:

- Understand when Spring resolves `@Bean` parameters and how they differ from regular Java method parameters.
- Use required dependencies, `@Qualifier`, `@Primary`, `Optional<T>`, `ObjectProvider<T>`, and collection injection with the right semantics.
- Distinguish `@Bean` parameters from directly calling `@Bean` methods in full/lite configuration.
- Handle missing beans, multiple candidates, dependency cycles, lifecycle/scope, and early initialization.
- Compile and run a Java 17+ example with Spring Framework 6, Gradle, and verifiable stdout.

## 2. How Does Spring Process `@Bean` Parameters?

For a bean to be created from a `@Bean` method, Spring registers a **bean definition** carrying the factory method metadata. When the container needs to create that bean, it selects the appropriate factory invocation, inspects each parameter, and resolves dependencies from the BeanFactory.

```text
@Configuration / @Bean is processed
             |
             v
  Register bean definition
     for factory method
             |
             v
   When target bean is needed
             |
             v
  Inspect @Bean parameters
   - Data type / generics
   - Qualifiers / annotations
   - Optional / provider / collections
             |
             v
    BeanFactory searches candidates
       /          |          \
     None       One bean    Multiple beans
       |          |           |
  required?     select     Primary/Qualifier/
       |          |        resolution rules
       v          v           v
   Error or   Invoke factory method with resolved dependencies
   valid          |
   value          v
             Object is created
                |
                v
        Spring manages lifecycle
```

Example `@Bean OrderService orderService(Repository repository)`:

- `Repository` is a **required dependency** unless expressed as optional.
- Spring searches for a bean matching `Repository`; if exactly one valid candidate exists, the factory method is invoked.
- If no bean exists and no suitable optionality policy applies, the context typically reports `UnsatisfiedDependencyException` with a cause related to `NoSuchBeanDefinitionException`.
- If multiple beans of the same type cannot be narrowed down to one candidate, `NoUniqueBeanDefinitionException` typically appears in the exception chain.
- If the factory method itself throws an exception while running, that is a **factory execution error**; do not confuse it with Spring failing to find a dependency.

**You do not need to put `@Autowired` on a `@Bean` method just for its parameters to be injected.** Parameter resolution is part of the mechanism for creating beans from factory methods. On a regular Java constructor, Spring also supports constructor injection; however, `@Bean` parameters belong to the **factory method called by the container**, not the constructor of the created object's class.

### 2.1. Bean definition and method invocation are two phases

Reading `@Bean` metadata does not mean the factory method already ran during configuration scanning. By default, many non-lazy singletons are pre-instantiated when `ApplicationContext` refreshes; if the target bean is marked `@Lazy` or uses another scope, the timing of factory invocation may differ.

In all cases, Spring must resolve parameters **before the factory method can execute**. A dependency error can prevent the method body from running at all.

## 3. Required Dependencies: Passing by Type

Given:

```java
@Bean
TaxCalculator taxCalculator() {
    return new TaxCalculator(10);
}

@Bean
CheckoutService checkoutService(TaxCalculator calculator) {
    return new CheckoutService(calculator);
}
```

Spring sees that `CheckoutService` created by `checkoutService(...)` has a parameter of type `TaxCalculator`, so it resolves the matching bean. The signature expresses the dependency relationship. You do not need to write:

```java
// Not recommended as a default:
@Bean
CheckoutService checkoutService() {
    return new CheckoutService(taxCalculator());
}
```

Both snippets are **separate illustrative code**, using application-specific `TaxCalculator` and `CheckoutService` classes. The important difference:

- With a **`@Bean` parameter**, Spring resolves the dependency through the container.
- With a **Java call `taxCalculator()`**, behavior depends on whether the configuration class is proxied; in `proxyBeanMethods = false` mode, this is just a regular Java call and can create an instance outside the expected singleton lookup mechanism.
- Parameterized signatures work naturally in both full and lite configurations without relying on method call interception.

A clean configuration typically prefers:

```java
@Configuration(proxyBeanMethods = false)
class CleanConfig {

    @Bean
    TaxCalculator taxCalculator() {
        return new TaxCalculator(10);
    }

    @Bean
    CheckoutService checkoutService(TaxCalculator calculator) {
        return new CheckoutService(calculator);
    }
}
```

This is an **illustrative** excerpt, not a standalone compilable Java file until the types are declared.

### 3.1. Method declaration order is not dependency order

`@Bean CheckoutService checkoutService(TaxCalculator calculator)` can appear **before** `@Bean TaxCalculator taxCalculator()` in the file. Spring builds the dependency graph from bean definitions and method parameters. Reordering two methods is not how you design initialization order.

If A depends on B, B must be prepared in order to construct A. That is a dependency relationship. `@Order` is used for ordering inside collections or certain extension points, **not as a replacement for constructor/factory dependencies** to guarantee singleton initialization order.

## 4. Multiple Beans of the Same Type: `@Qualifier` and `@Primary`

Suppose there are two implementations of `FeePolicy`:

```java
@Bean
@Qualifier("standard")
FeePolicy standardFee() {
    return new FixedFeePolicy("standard", 5);
}

@Bean
@Qualifier("express")
FeePolicy expressFee() {
    return new FixedFeePolicy("express", 15);
}
```

Both methods return the same `FeePolicy` interface. A method:

```java
@Bean
CheckoutService checkoutService(FeePolicy policy) {
    return new CheckoutService(policy);
}
```

can hit an ambiguous dependency error if Spring cannot determine a single winning candidate. You need to specify the **exact role** of the dependency:

```java
@Bean
CheckoutService checkoutService(
        @Qualifier("standard") FeePolicy policy) {
    return new CheckoutService(policy);
}
```

These snippets are **illustrative only**: the `FeePolicy` and `FixedFeePolicy` types are defined in the complete example in section 8. `@Qualifier` on a parameter acts as a filter condition: Spring looks for candidates matching both the type and the qualifier. A qualifier can be placed on the bean factory method and on the injected parameter; a qualifier cannot make a bean of the wrong type match.

**Point to remember:** the method name `standardFee` and the qualifier label `standard` are different things; do not treat the two concepts as identical. If a matching bean name exists, Spring can use the bean name as a fallback qualifier; however, placing `@Qualifier("standard")` on both the bean declaration and the usage site expresses the business role more clearly.

### 4.1. `@Primary` as the default policy

You can annotate:

```java
@Bean
@Primary
FeePolicy standardFee() {
    return new FixedFeePolicy("standard", 5);
}
```

When a caller injects a `FeePolicy` without a qualifier and multiple candidates of the same type exist, `@Primary` prioritizes this bean if it is the sole primary among the candidates. With `@Qualifier("express") FeePolicy policy`, Spring can still choose the express bean if only express matches the qualifier; the standard bean's primary status does not let it override a non-matching qualifier.

Marking **two primaries that are both considered** does not automatically resolve ambiguity. On a `@Bean` method with a single required parameter, use a qualifier when the role is specific and primary for a genuinely sensible default.

### 4.2. `@Bean` return type affects candidate discovery

Spring uses type metadata from the bean definition, including the declared return type of the `@Bean` method, to resolve autowiring. Therefore declare a return type that is **sufficiently specific** and matches the contract:

```java
@Bean
PaymentClient paymentClient() {
    return new DefaultPaymentClient();
}
```

If a factory method returns an overly broad type like `Object`, an injection point requesting `PaymentClient` may not be fully recognized by Spring from type metadata before the target bean is instantiated. In many situations, declare an interface/abstract type useful to consumers, or the concrete class if callers genuinely need that API. Do not rely on the runtime type of the returned object to completely substitute for bean definition type metadata.

This is an illustrative snippet; `PaymentClient` and `DefaultPaymentClient` must be defined.

## 5. Optional Parameters: `Optional` and `ObjectProvider`

Not every dependency needs to be present. A payment service might emit audit records if an audit module is present, and still work if auditing is disabled.

### 5.1. `Optional<T>`: decided at bean creation time

```java
@Bean
ReportService reportService(Optional<AuditSink> auditSink) {
    return new ReportService(auditSink);
}
```

With `java.util.Optional`, Spring can inject `Optional.empty()` when no candidate exists. If exactly one `AuditSink` is resolved, the value is `Optional.of(bean)`. If multiple `AuditSink` beans cannot be narrowed down, optionality should not be misunderstood as a rule to silently pick a bean at random; an ambiguity error can still occur.

`Optional<T>` fits when the factory method wants to decide once at bean creation time whether the dependency is available. For instance, `ReportService` can hold `Optional<AuditSink>` as configuration state at service construction time.

**Note:** In a singleton, injecting `Optional<T>` does not automatically make the service "observe" later changes to the bean registry.

### 5.2. `ObjectProvider<T>`: resolved on demand

```java
@Bean
ReportService reportService(ObjectProvider<AuditSink> auditProvider) {
    return new ReportService(auditProvider);
}
```

Spring can inject the provider without needing to find a concrete `AuditSink` immediately inside `ReportService`'s factory method. Business code later chooses how to handle it:

```java
AuditSink required = auditProvider.getObject();
AuditSink optional = auditProvider.getIfAvailable();
AuditSink unique = auditProvider.getIfUnique();
```

This is an illustrative snippet using an already-provided `auditProvider` variable; it is **not standalone** without the `AuditSink` class and variable declaration.

| Method | No bean | One winning candidate | Multiple unresolved candidates |
| --- | --- | --- | --- |
| `getObject()` | Throws `NoSuchBeanDefinitionException` | Returns bean | Throws `NoUniqueBeanDefinitionException` |
| `getIfAvailable()` | `null` | Returns bean | Throws `NoUniqueBeanDefinitionException` |
| `getIfUnique()` | `null` | Returns bean | `null` |

If multiple beans exist and a matching `@Primary` bean is chosen by Spring as the winning candidate, all three methods can return that bean. If business logic needs lazy lookup or handling an optional dependency at usage time, a provider expresses that cleanly.

**Do not equate a provider with a lazy singleton:** another non-lazy singleton `AuditSink` may already have been created by Spring during context refresh. A provider only makes the timing of **lookup from the consumer** flexible; to deliberately defer bean instantiation, you also need to examine `@Lazy` and the dependency graph.

### 5.3. Using `@Nullable` and intentional null

Spring supports other ways to represent optional dependencies depending on nullability annotations and version. In Spring Framework 6.2, `@Nullable` is supported at injection points through the appropriate mechanism. When writing Java 17, `Optional<T>` or `ObjectProvider<T>` usually communicates intent more clearly than a nullable parameter whose method body forgets to check for `null`.

Do not mark every dependency `@Nullable` merely so context startup succeeds: for required dependencies, a missing-bean error is an important configuration signal.

## 6. Collection Parameters: A Factory Method Needing a Group of Beans

A method can receive multiple beans of the same type:

```java
@Bean
Pipeline pipeline(List<Handler> handlers) {
    return new Pipeline(handlers);
}
```

Spring gathers beans matching `Handler` into a `List<Handler>`; if ordering metadata is present, list order is typically determined by `Ordered`, `@Order`, or `@Priority` as applicable. The method body does not have to call `getBeansOfType` or iterate bean names manually.

You can also use:

- `Handler[]`: an array of matching beans;
- `Set<Handler>`: a group of beans with set semantics, without relying on iteration order as a strict pipeline order;
- `Map<String, Handler>`: a map with **bean name** as key and bean as value;
- `@Qualifier("fraud") List<Handler>`: the set of `Handler` beans matching the `fraud` qualifier.

**`@Primary` does not filter collection elements**; primary only aids in selecting one bean when a single dependency needs resolution. When a factory method accepts `List<Handler>`, it declares that the new bean needs **the entire group of handlers**, not a single default handler.

### 6.1. When the collection has no members

Do not assume every factory method accepting `List<T>` will automatically receive `List.of()` when no beans exist. At a required dependency injection point, Spring may treat finding no matching beans as an error. If "no handlers" is a normal business case, design optionality explicitly (for example using `ObjectProvider<Handler>` and `orderedStream()`, then building the list) and test the behavior of your Spring version.

### 6.2. Distinguishing a multi-bean collection from an existing collection bean

`@Bean Pipeline pipeline(List<Handler> handlers)` in the typical example asks Spring to **collect `Handler` beans**. In cases where the application also declares a bean whose own type is `List<Handler>`, collection bean selection behavior can differ: you must clarify whether you want to inject **one bean of type List** or **multiple `Handler` elements**. Design names, qualifiers, and generic types clearly, and test the real context when both styles coexist.

## 7. Factory Method Parameters vs. Calling `@Bean` Methods Directly

This is one of the most important distinctions in Java-based configuration.

### 7.1. Full `@Configuration` and `proxyBeanMethods=true`

With standard configuration:

```java
@Configuration
class FullConfig {

    @Bean
    Engine engine() {
        return new Engine();
    }

    @Bean
    Car car() {
        return new Car(engine());
    }
}
```

This is an **illustrative snippet** requiring `Engine` and `Car` classes. `@Configuration`'s default `proxyBeanMethods=true` allows Spring to enhance the configuration class (typically via CGLIB) to **intercept calls between `@Bean` methods**, enforcing container semantics—for example returning the registered singleton instead of arbitrarily executing `new Engine()` when called through the proxy.

This mechanism imposes constraints on enhancing classes and methods, and makes configuration code depend on proxy semantics. Hence, even with full `@Configuration`, passing dependencies via parameters is usually easier to understand.

### 7.2. `proxyBeanMethods=false` and lite configuration

With:

```java
@Configuration(proxyBeanMethods = false)
class LiteConfig {

    @Bean
    Engine engine() {
        return new Engine();
    }

    @Bean
    Car car() {
        return new Car(engine());
    }
}
```

The `engine()` call inside `car()` is an **ordinary Java call**, which can create a new `Engine` outside the singleton instance managed by the BeanFactory. `@Bean` methods are still processed by Spring to register beans, but direct method calls are not intercepted by a proxy.

Clearer style:

```java
@Configuration(proxyBeanMethods = false)
class ParameterConfig {

    @Bean
    Engine engine() {
        return new Engine();
    }

    @Bean
    Car car(Engine engine) {
        return new Car(engine);
    }
}
```

These are three **separate** illustrative templates; do not combine them in one file/class without defining `Engine`/`Car`. With `ParameterConfig`, `car`'s dependency is obtained from the container; there is no need for the engine method to be called directly.

### 7.3. Can you call a `@Bean` method directly in Java?

You *can* call it like a normal Java method, yet the behavior depends on how the configuration class was created and its proxy mode. In particular, calling a method on a configuration instance created with `new` outside Spring does not make Spring inject parameters and does not turn the returned object into a managed bean. Therefore do not treat `@Bean` as a "magic factory" that obeys container semantics in every Java call.

**Practical rule:** when bean A needs bean B, write `@Bean A a(B b)`. Do not default to `@Bean A a() { return new A(b()); }` when passing B as a parameter is possible.

## 8. Full Runnable Java 17+ Example with Spring Context 6

The following project demonstrates five properties:

1. A required parameter resolved from the `PriceCalculator` bean.
2. `@Qualifier("standard")` selecting one specific `FeePolicy` when two beans share the same type.
3. `ObjectProvider<AuditSink>` expressing optional auditing capability.
4. `Optional<AuditSink>` yielding a valid absent value.
5. `List<FeePolicy>` receiving both policies ordered by `@Order` on the factory methods.

The example needs no Spring Boot, HTTP, database, or external configuration. `@Configuration(proxyBeanMethods=false)` is chosen intentionally to prove **method parameters are sufficient to express dependencies**.

### 8.1. Project structure

```text
bean-method-parameters-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/
    └── BeanMethodParametersDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'bean-method-parameters-demo'
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
    implementation 'org.springframework:spring-context:6.2.18'
}

application {
    mainClass = 'BeanMethodParametersDemo'
}
```

Use JDK 17+ and a Gradle version compatible with the running JDK. `spring-context` brings in the Spring modules needed for `AnnotationConfigApplicationContext`, `@Bean`, `@Qualifier`, `ObjectProvider`, and collection autowiring.

### 8.2. Complete source code

File `src/main/java/BeanMethodParametersDemo.java`:

```java
import java.util.List;
import java.util.Optional;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;

public class BeanMethodParametersDemo {

    record FeePolicy(String name, int surcharge) {
    }

    record PriceCalculator(int taxPercent) {
        int total(int amount, FeePolicy fee) {
            return amount + amount * taxPercent / 100 + fee.surcharge();
        }
    }

    interface AuditSink {
        void record(int total);
    }

    record CheckoutService(
            PriceCalculator calculator,
            FeePolicy selected,
            ObjectProvider<AuditSink> auditProvider) {

        int quote(int amount) {
            int total = calculator.total(amount, selected);
            auditProvider.ifAvailable(sink -> sink.record(total));
            return total;
        }
    }

    record FeeCatalog(
            List<FeePolicy> all,
            Optional<AuditSink> audit) {

        List<String> names() {
            return all.stream().map(FeePolicy::name).toList();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {

        @Bean
        PriceCalculator priceCalculator() {
            return new PriceCalculator(10);
        }

        @Bean
        @Order(10)
        @Qualifier("standard")
        FeePolicy standardFee() {
            return new FeePolicy("standard", 5);
        }

        @Bean
        @Order(20)
        @Qualifier("express")
        FeePolicy expressFee() {
            return new FeePolicy("express", 15);
        }

        @Bean
        CheckoutService checkoutService(
                PriceCalculator calculator,
                @Qualifier("standard") FeePolicy selected,
                ObjectProvider<AuditSink> auditProvider) {
            return new CheckoutService(calculator, selected, auditProvider);
        }

        @Bean
        FeeCatalog feeCatalog(
                List<FeePolicy> allFees,
                Optional<AuditSink> audit) {
            return new FeeCatalog(List.copyOf(allFees), audit);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            var catalog = context.getBean(FeeCatalog.class);
            var checkout = context.getBean(CheckoutService.class);

            System.out.println("policies = " + catalog.names());
            System.out.println("selected = " + checkout.selected().name());
            System.out.println("quote100 = " + checkout.quote(100));
            System.out.println("optionalAudit = " +
                    catalog.audit().isPresent());
            System.out.println("providerAudit = " +
                    (checkout.auditProvider().getIfAvailable() != null));
            System.out.println("sameCheckout = " +
                    (checkout == context.getBean(CheckoutService.class)));
        }
    }
}
```

### 8.3. Run command

Inside the `bean-method-parameters-demo` directory:

```bash
gradle run --quiet
```

If using the Gradle Wrapper:

```bash
./gradlew run --quiet
```

On Windows PowerShell, substitute `.\gradlew.bat run --quiet`.

Stdout produced by the `System.out.println` statements in the code:

```text
policies = [standard, express]
selected = standard
quote100 = 115
optionalAudit = false
providerAudit = false
sameCheckout = true
```

Gradle messages or environment logging (if configured separately) are not part of the business stdout above.

### 8.4. Analyzing each result

**`policies = [standard, express]`**: `feeCatalog(List<FeePolicy> allFees, ...)` receives both `FeePolicy` beans; the two factory methods carry `@Order(10)` and `@Order(20)`, so the list is ordered accordingly. The two beans are created independently yet share the `FeePolicy` interface/type.

**`selected = standard`**: the `@Qualifier("standard") FeePolicy selected` parameter of `checkoutService(...)` filters down to the policy labeled `standard`. Removing the qualifier while two equal candidates exist can cause the method to fail when Spring attempts to resolve a single `FeePolicy`.

**`quote100 = 115`**: `PriceCalculator(10)` computes 10% tax on 100 as 10; the standard fee is 5; total `100 + 10 + 5 = 115`. `auditProvider.ifAvailable(...)` does not execute the consumer because the context declares no `AuditSink` bean.

**`optionalAudit = false`**: `feeCatalog(...)` receives `Optional.empty()`; the absence of `AuditSink` is a valid part of the design.

**`providerAudit = false`**: the provider is injected successfully, yet `getIfAvailable()` at call time returns `null` since no `AuditSink` bean exists.

**`sameCheckout = true`**: `CheckoutService` is created by `@Bean` with the default singleton scope; two `getBean(...)` calls receive the same instance within a context.

**Core evidence:** `checkoutService(...)` never calls `priceCalculator()` or `standardFee()`, and `feeCatalog(...)` does not query the bean registry directly. Spring resolves the parameters as part of invoking the factory.

### 8.5. Experiments to observe

**Experiment 1 — Add an audit bean.** Add to `Config`:

```java
@Bean
AuditSink auditSink() {
    return total -> System.out.println("audit = " + total);
}
```

This is an **addition to the example in section 8**, not a standalone file. Now `Optional<AuditSink>` has a value and the provider also resolves `AuditSink`; `checkout.quote(100)` will additionally print `audit = 115` from the consumer before `main`'s `quote100 = 115` line.

**Experiment 2 — Remove `@Qualifier("standard")` from the single parameter.** Spring has two `FeePolicy` beans and no primary. On context refresh, Spring may fail to choose a single winner and report ambiguity. Do not rely on the parameter being named `selected` to pick one of the two.

**Experiment 3 — Add `@Primary` on `standardFee()`.** For the unqualified single parameter `FeePolicy selected`, Spring can pick standard as default if it is the sole primary. However, `FeeCatalog`'s `List<FeePolicy>` **still contains both standard and express**.

**Experiment 4 — Change `@Order`.** Change standard's `@Order(10)` to `@Order(30)`. With express ordered at 20, the list in `FeeCatalog` changes to `[express, standard]`; the qualifier selecting standard for `CheckoutService` remains unchanged. This shows that **filtering beans** and **ordering a collection** are two distinct decisions.

## 9. Dependency Cycles and Initialization Failures

Factory method parameters express a dependency graph. If there is a cycle A -> B -> A, Spring cannot create two singletons with hard constructor/factory dependencies in a normal linear order.

Intentionally broken example:

```java
@Configuration(proxyBeanMethods = false)
class CyclicConfig {

    @Bean
    A a(B b) {
        return new A(b);
    }

    @Bean
    B b(A a) {
        return new B(a);
    }
}
```

This is an **error-demonstrating excerpt**, requiring classes `A` and `B`. When the container tries to create A, it needs B; creating B in turn needs A. With this kind of hard dependency, Spring typically reports circular reference / bean currently in creation, which may be wrapped in `UnsatisfiedDependencyException` or `BeanCreationException` depending on the path.

**The preferred fix is correcting the design:** split responsibilities, invert dependencies, or extract a cycle-free interface/event/collaborator. `ObjectProvider<T>` or `@Lazy` can defer one link in some cases, yet they do not guarantee the logical cycle is safely resolved; if methods invoke each other endlessly at runtime, deferring injection will not cure it.

### 9.1. Missing bean because configuration was not registered

Putting `@Bean` inside a class that Spring has not registered/imported/scanned will not make the bean definition appear automatically. When method A requires parameter B, Spring can only resolve B from **the current container** (including registration sources visible to the context), not from arbitrary Java classes in the project.

When a dependency is missing, check:

- Was the configuration class passed to `AnnotationConfigApplicationContext`, `@Import`, or scanned?
- Is the `@Bean` method actually processed by Spring, or is it just a Java method outside the container?
- Is there a `@Profile`, `@Conditional`, or filter excluding the bean?
- Does the declared `@Bean` return type match the requested parameter type?
- Are there multiple beans of the same type without a qualifier?
- Is the dependency on the runtime classpath and available at refresh time?

### 9.2. Errors in the method body

Spring may resolve all parameters successfully yet the method still throws `IllegalStateException`, fails an API call, or returns an unexpected object. The failure message may then be `BeanCreationException` mentioning the factory method. To debug, inspect the **root cause** and distinguish "argument resolution failed" from "factory execution failed".

Do not catch broad exceptions inside `@Bean` and return `null` to hide errors: the container has specific semantics when a factory method returns `null`, and callers can see very unexpected results. For required beans, surface configuration failures clearly.

## 10. Scope, Lazy, and Bean Creation Order

### 10.1. Singleton does not mean any arbitrary Java call

`@Bean` by default creates a container-managed singleton. If method A has parameter B, the container supplies the appropriate B instance. That does not mean spontaneous calls to `config.b()` in every proxy mode will return the singleton; that is why parameter injection is the reliable idiom.

### 10.2. Prototypes are resolved when creating the consumer

If bean B has `@Scope("prototype")` and singleton A receives B as a **factory method parameter**, Spring creates one prototype instance when constructing A; A normally retains that same reference afterward rather than receiving a new prototype on every business method call.

To get a fresh prototype on each use, accept `ObjectProvider<B>` as the dependency and call `getObject()` each time it is needed, matching the scope/contract. This is a lifecycle policy, not merely parameter syntax.

### 10.3. `@Lazy` does not replace the dependency graph

Putting `@Lazy` on a bean definition can defer initialization until needed. However, if another singleton being instantiated eagerly takes the lazy bean **as a required `@Bean` parameter**, dependency resolution can still trigger immediate creation of the lazy bean. To defer lookup from a consumer, `ObjectProvider<T>` or an appropriate proxy must be evaluated separately.

### 10.4. `@DependsOn` for ordering dependencies not expressed via parameters

If A needs B to build its object, write `@Bean A a(B b)`. If A does not need a reference to B yet wants B initialized first to prepare an intentional side effect, `@DependsOn("b")` can express this ordering requirement.

```java
@Bean
@DependsOn("migrationRunner")
ReportCache reportCache() {
    return new ReportCache();
}
```

This is an illustrative snippet requiring a bean named `migrationRunner`, class `ReportCache`, and imports. `@DependsOn` relies on **bean name**, not type; it does not replace constructor/factory parameter injection for actual object dependencies.

## 11. Comparison with Other Ways to Express Dependencies

| Approach | Where is the dependency declared? | When to choose |
| --- | --- | --- |
| Constructor injection on `@Component`/`@Service` | Class constructor | Class belongs to your codebase and can carry stereotypes; required dependencies belong to the object itself |
| `@Bean` method parameter | Factory method signature in Java configuration | Creating objects via a factory, integrating library classes, or controlling construction |
| `@Bean` method calling another `@Bean` method | Method body | Can be valid in full config, yet easily depends on proxy semantics |
| Direct `ApplicationContext.getBean(...)` | Imperative lookup code | Infrastructure code genuinely needing dynamic lookup; avoid service locator in business code |
| `@DependsOn` | Bean-name metadata | Initialization ordering needed for side effects without a direct object parameter |
| Injected `ObjectProvider<T>` | Factory method/constructor accepting provider | Target may be absent, needs delayed lookup, or needs dynamic scope |

There is no single mandatory style for all applications. Yet when using `@Bean` factory methods, **declaring parameters is the natural way to express dependencies**: explicit contract, avoids looking up beans by string names, and minimizes reliance on CGLIB interception of the configuration class.

## 12. Common Mistakes and Fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| `UnsatisfiedDependencyException` creating bean from `@Bean` | Missing bean for required parameter | Register/import config supplying the bean; check type, profile, condition |
| `NoUniqueBeanDefinitionException` | Multiple candidates of the same type without a winner | Add `@Qualifier` on parameter, designate an appropriate `@Primary`, or adjust design |
| One bean has `@Primary` yet qualifier picks another bean | Qualifier filters the candidate set before priority applies | Check qualifiers on both the declaring method and the parameter |
| Directly called `@Bean` method returns an instance other than the expected singleton | Using `proxyBeanMethods=false` or calling config class outside Spring | Use `@Bean` parameters instead of direct calls |
| Adding `@Autowired` on `@Bean` thinking it is required | Misunderstanding factory method argument resolution | Remove redundant annotation; Spring resolves `@Bean` parameters automatically |
| Beans in context do not see another method | Configuration not processed, outside scan/import | Register the configuration into the right context |
| `@Lazy` enabled yet bean is still created early | Another bean requires it as a mandatory dependency at startup | Use an appropriate provider/proxy or adjust the dependency graph |
| Prototype not newly created on each business method call | Prototype was resolved once when singleton was built | Inject `ObjectProvider<Prototype>` and look up when needed |
| Using `@Order` to "force bean B to init before A" | `@Order` does not express singleton initialization dependencies | Declare `@Bean A a(B b)` or `@DependsOn` for side effects |
| `@Bean` method accepts `List<T>` yet has zero elements | Required dependency not satisfied | Use `ObjectProvider<T>`/stream when empty is permitted by contract |
| Using `Optional<T>` and still seeing ambiguity | Optional allows absence, does not pick arbitrarily from multiple beans | Use qualifier, primary, or handle multi-candidate policy |
| `ObjectProvider<T>` is present yet `getObject()` fails | Provider only defers target resolution | Choose `getIfAvailable()`/`getIfUnique()` if policy permits; fix config if required |
| Configuring two beans creates a dependency cycle | Factory parameters A -> B -> A | Refactor dependency graph; do not use proxies to mask logic flaws |
| Factory parameter fails to resolve by concrete class | Bean type metadata too broad (`Object`) or generic mismatch | Use a clear contract return type; inspect `ResolvableType` if needed |
| Writing `@Bean` then calling the method on `new Config()` | Calling a Java object outside Spring | Retrieve managed bean from `ApplicationContext`/inject into consuming beans |

**Useful debugging technique:** focus on which `@Bean` method Spring is invoking, which parameter failed, and which bean names/candidate types exist in the context. Reading only the method body is insufficient if Spring cannot resolve an argument.

## 13. Practice Exercises and Answers

### Exercise 1 — Eliminating direct `@Bean` method calls

Given:

```java
@Configuration(proxyBeanMethods = false)
class OldConfig {
    @Bean
    ReportRepository repository() {
        return new ReportRepository();
    }

    @Bean
    ReportService service() {
        return new ReportService(repository());
    }
}
```

Rewrite so `ReportService` uses the repository managed by Spring.

**Answer:**

```java
@Bean
ReportService service(ReportRepository repository) {
    return new ReportService(repository);
}
```

These are two **illustrative excerpts** using self-defined classes. Spring resolves the repository by type while creating the service; the method does not need to call `repository()` directly.

### Exercise 2 — Two candidates implementing the same interface

The configuration has `@Bean @Qualifier("email") Notifier email()` and `@Bean @Qualifier("sms") Notifier sms()`. You want `@Bean AlertManager manager(...)` to receive SMS.

**Answer:** declare `@Bean AlertManager manager(@Qualifier("sms") Notifier notifier)`, then invoke the constructor with `notifier`. Do not rely on method order or manually call `new SmsNotifier()`.

### Exercise 3 — Extending the demo with auditing

Add `@Bean AuditSink auditSink()` as in section 8.5. Predict:

- `catalog.audit().isPresent()` becomes `true`;
- `checkout.auditProvider().getIfAvailable() != null` becomes `true`;
- calling `checkout.quote(100)` triggers the audit consumer with total 115.

Passing `Optional` and the provider in the factory method **requires no changes**.

### Exercise 4 — Swapping the positions of two factory methods

Move `checkoutService(...)` to the top of `Config` before `priceCalculator()`. Does that make Spring lose the calculator bean?

**Answer:** No, as long as both `@Bean` methods are processed and the dependency graph has no errors. Spring resolves via bean definitions, not textual file order.

### Exercise 5 — Default policy and collections

Add `@Primary` to the standard bean while keeping express. If you write:

```java
@Bean
FeeCatalog feeCatalog(List<FeePolicy> policies) {
    return new FeeCatalog(policies, Optional.empty());
}
```

This is an **illustrative variant** of the demo (if replacing `feeCatalog`). How many elements does the list contain?

**Answer:** Both `FeePolicy` beans; primary does not filter collections. They can still be ordered with `@Order` as before.

### Exercise 6 — Singleton needing a prototype

`@Bean A a(B prototypeB)` injects a B instance into singleton A. If B has prototype scope, does every call to `a.run()` automatically receive a new B?

**Answer:** No. A holds the B resolved when A was constructed. To obtain a fresh B per usage, design A to accept `ObjectProvider<B>` and look it up.

### Exercise 7 — A/B cycle

Two factory methods `A a(B b)` and `B b(A a)` both create singletons with no deferral mechanism. What happens?

**Answer:** The container cannot satisfy both hard dependencies; it typically fails with circular creation/unsatisfied dependency. Refactor the graph or replace the synchronous relationship with a suitable design.

### Exercise 8 — Distinguishing missing dependency from factory error

Method:

```java
@Bean
ReportService reportService(Repository repository) {
    throw new IllegalStateException("broken factory");
}
```

If Spring has a valid repository, where does initialization fail?

**Answer:** Spring successfully resolves the parameter, and then the method body throws `IllegalStateException`. This is a factory execution error, not a missing `Repository` bean.

### Exercise 9 — Optional does not mean arbitrary selection

There are two equal `AuditSink` beans while the method accepts `Optional<AuditSink>`. Is it guaranteed to receive `Optional.empty()`?

**Answer:** No. `Optional.empty()` expresses **absence of a dependency**, not a policy for ignoring ambiguity across multiple candidates. Filter with a qualifier or adopt an appropriate selection policy.

### Exercise 10 — Choosing how to express dependencies

A library provides an `HttpClientAdapter` class without stereotypes; the application creates it with `@Bean` and it needs a `CredentialsProvider` bean. Should you call `context.getBean(CredentialsProvider.class)` inside the method or add a `CredentialsProvider credentials` parameter?

**Answer:** Add the method parameter `@Bean HttpClientAdapter adapter(CredentialsProvider credentials)`. That clarifies the dependency and makes testing easier without relying on a Service Locator.

## 14. Checklist When Writing `@Bean` Methods

- Which objects does the bean being created depend on? Put **required dependencies** in factory method parameters.
- Are there multiple candidates of the same type? Use `@Qualifier` for specific roles, `@Primary` when a default is needed.
- Are there optional dependencies? Use `Optional<T>` or `ObjectProvider<T>` according to resolution timing and business policy.
- Does the bean need an entire group of implementations? Use `List<T>`/array or a provider stream; do not add primary expecting only one element to remain.
- Are you directly calling another `@Bean` method? Consider replacing it with a parameter so you do not rely on proxy mode.
- Is the `@Bean` return type explicit enough for by-type resolution?
- Is there an A -> B -> A cycle, or could factory method side effects/I/O cause startup failures?
- Do scope and lazy policies match object creation and usage timing?
- Is the configuration class actually registered/imported/scanned by the container?
- Have you verified it with a small `ApplicationContext` and checked the injection results?

## 15. Takeaways and Reading Resources

- **`@Bean` parameters are dependencies resolved by Spring** right before the container invokes the factory method.
- **`@Autowired` is not required on a `@Bean` method** to inject parameters.
- **Single dependencies** are selected by type, qualifier, primary, and resolution rules; absence or ambiguity can cause bean creation to fail.
- **Optional/provider/collection** let you express different needs: valid absence, delayed lookup, or multiple beans of the same type.
- **Method parameters** work cleanly with `@Configuration(proxyBeanMethods=false)`; direct calls to `@Bean` methods have different semantics depending on proxy mode.
- **Scope/lifecycle and the dependency graph** determine when beans are created; `@Order` does not replace constructor/factory dependencies.
- A factory method with explicit parameters is usually much easier to read than injecting `ApplicationContext` just to fetch each dependency manually.

Official documentation:

- [Spring Framework Reference — Using the `@Bean` Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html).
- [Spring Framework Reference — Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html).
- [Spring Framework Reference — Using `@Autowired`](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html).
- [Spring Framework Reference — Fine-tuning Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html).
- [Spring Framework Reference — Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html).
- [Spring Framework Javadoc — `ObjectProvider`](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/ObjectProvider.html).
