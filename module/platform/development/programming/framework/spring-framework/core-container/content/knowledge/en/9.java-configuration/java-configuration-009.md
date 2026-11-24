# `final`, `private`, and `static` Limitations When Spring Intercepts `@Bean` Calls

## 1. The Problem: Why Are Some `@Bean` Methods Intercepted While Others Are Not?

In Spring Java Configuration, the `@Bean` annotation marks a factory method so the Spring IoC Container registers and manages the returned object. However, not every **direct Java call** to a `@Bean`-annotated method has the same semantics as looking up a bean from the container. The difference lies in the configuration class's processing mode and the ability to **override methods with CGLIB**.

Example:

```java
@Configuration
class AppConfig {
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

This is **illustrative** code, not a standalone program because `Engine`/`Car` and imports are not defined. When `AppConfig` is registered with Spring in **full configuration mode** (default `proxyBeanMethods = true`), the `engine()` call from `car()` on the Spring-enhanced instance is typically routed to `BeanFactory`. If `engine` is a singleton, `Car` receives a reference to the container-managed `engine` bean.

Yet there are three important groups of constraints:

- **`final`**: Java forbids subclassing a `final` class or overriding a `final` method.
- **`private`**: `private` methods cannot be overridden by a subclass method.
- **`static`**: class-level methods do not participate in instance virtual dispatch/overriding; therefore direct calls to `static @Bean` methods are **not routed to BeanFactory by the CGLIB interceptor**.

This does **not mean** `@Bean` with `static` is always wrong: static `@Bean` is a supported case in Spring, particularly useful for creating certain post-processors early. Meanwhile `final` and `private` on instance `@Bean` methods are notable constraints of **full `@Configuration`**; do not carry those exact restrictions over to **lite mode**.

Lesson objectives:

1. Understand full vs. lite configuration and why CGLIB is used.
2. Distinguish restrictions on the **class** from restrictions on **instance factory methods**.
3. Explain why static `@Bean` is valid yet lacks inter-bean call interception.
4. Use `proxyBeanMethods = false` and factory-method parameter injection properly.
5. Know when static `@Bean` is needed for `BeanFactoryPostProcessor`/`BeanPostProcessor`.
6. Run a Java 17+ example comparing identity/instance counts to spot configuration errors.

## 2. Full and Lite Differ in Overridability

Spring registers and manages beans from `@Bean` in both modes. Full mode (default `@Configuration`) uses a CGLIB subclass to intercept eligible instance factory methods on the enhanced configuration bean; lite mode (`proxyBeanMethods=false`) lets direct method calls execute with ordinary Java semantics.

### 2.1. Full mode requires overridable instance methods

```java
@Configuration
class FullConfig {
    @Bean Engine engine() { return new Engine(); }
    @Bean Car car() { return new Car(engine()); }
}
```

This illustrative snippet requires `Engine` and `Car` types. When Spring invokes `car()` through the enhanced configuration, `engine()` can be routed to BeanFactory to fetch the singleton. To do so, CGLIB must subclass the configuration and override the method.

### 2.2. Lite mode allows plain Java direct calls

If you change the annotation to `@Configuration(proxyBeanMethods=false)`, `engine()` inside `car()` executes directly and can construct an object different from the managed `engine`. Switch to `car(Engine engine)` so Spring resolves the dependency from BeanFactory.

### 2.3. Constraints table

| Element | Full | Lite |
| --- | --- | --- |
| `final` configuration class | Invalid because subclassing is required | Allowed |
| `private`/`final` instance `@Bean` method | Invalid because overriding is required | Allowed if Spring can invoke the method |
| `static @Bean` | Valid, no interception | Valid, no interception |
| `@Bean` parameters | Resolved by Spring | Resolved by Spring |

`proxyBeanMethods=false` does not disable DI, lifecycle, or singleton management for beans actually created by the container. The following sections explain **why each Java modifier alters interception capability**.

## 3. `final`: Forbids Inheritance and Forbids Overriding

Java `final` applies to classes or instance methods:

- `final class A`: no class can extend `A`.
- `final void action()`: subclasses cannot override `action()`.
- `final` on fields/local variables has a different meaning and is **not** a direct constraint of CGLIB method interception.

### 3.1. A `@Configuration` class cannot be `final` in full mode

**Intentionally invalid** example for full mode:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public final class InvalidFinalConfig {
    @Bean
    String serviceName() {
        return "billing";
    }
}
```

This illustrates `InvalidFinalConfig.java`, which compiles in Java yet is **unsuitable for full Spring configuration processing**. When Spring needs to generate a subclass of `InvalidFinalConfig`, the `final` modifier blocks inheritance; the context can fail during configuration class validation/processing before callers can retrieve beans.

Do not work around this by writing a subclass yourself or putting the annotation on another class expecting the final class to still be enhanced. There are two valid options:

1. Remove `final` from the configuration class if full-mode inter-bean calls are genuinely needed.
2. Switch to `@Configuration(proxyBeanMethods = false)` **if factory methods are independent** or dependencies are received via parameters.

Valid lite example in principle:

```java
@Configuration(proxyBeanMethods = false)
public final class FinalLiteConfig {
    @Bean
    String serviceName() {
        return "billing";
    }
}
```

This illustrates `FinalLiteConfig.java`; `@Configuration` and `@Bean` imports are needed if placed in a separate file. The `serviceName` bean is still managed by Spring; the `final` modifier simply means the class cannot be subclassed.

### 3.2. Instance `@Bean` methods cannot be `final` in full mode

**Intentionally invalid** example:

```java
@Configuration
class InvalidFinalMethodConfig {
    @Bean
    public final Engine engine() {
        return new Engine();
    }
}
```

`InvalidFinalMethodConfig` is not `final`, yet `engine()` cannot be overridden. Because full mode needs to intercept calls to that method, Spring treats this as invalid configuration. The error is typically reported while processing bean definitions, e.g. "`@Bean method ... must not be private or final`" or an equivalent version-specific message.

**Do not rely on the Java compiler to catch this error.** Java syntax permits a method to be both annotated and `final`; what is violated is the **Spring full configuration processing** contract. Test by creating an `AnnotationConfigApplicationContext` rather than merely running `javac`.

### 3.3. What about `final` on a business class returned from `@Bean`?

Example:

```java
public final class PricingRules {
    public int fee() {
        return 5;
    }
}

@Configuration
class ValidConfig {
    @Bean
    PricingRules pricingRules() {
        return new PricingRules();
    }
}
```

These are two **illustrative excerpts** corresponding to separate Java files. `ValidConfig` is not `final` and its factory method can be overridden. **The `PricingRules` class created as a bean can be `final`** without blocking **CGLIB enhancement of the configuration class**: Spring enhances `ValidConfig`, without necessarily subclassing `PricingRules`.

Distinguish this from needing a **Spring AOP class-based proxy** on `PricingRules` itself: a `final` target class can restrict AOP proxying because it cannot be subclassed. Both topics involve proxying mechanisms, yet **not the same object being subclassed**.

### 3.4. Java records and Kotlin

Java records are implicitly `final` classes, so **do not use a record as a full `@Configuration` class needing a CGLIB subclass**. With `@Configuration(proxyBeanMethods=false)`, these subclassing restrictions no longer stem from bean method interception; you still must ensure the framework can construct the configuration object properly.

In Kotlin, classes and methods are final by default; the Kotlin Spring / `all-open` plugin is typically used to open classes/annotations needing proxies. Still, do not rely on Kotlin tricks to mask a flawed dependency graph; lite mode and method-parameter injection remain helpful.

## 4. `private`: Method Exists, Yet Subclasses Cannot Override It

A `private` method is accessible only within its declaring scope per Java rules and is not inherited as an overridable virtual method. Therefore:

```java
@Configuration
class InvalidPrivateConfig {
    @Bean
    private Engine engine() {
        return new Engine();
    }
}
```

This is an **intentionally invalid** example in full mode. Because `engine()` is a private instance method, a CGLIB subclass cannot override it to intercept calls with container semantics. Spring full configuration validation rejects factory methods like this.

Do not try to "fix" this merely by adding `@Autowired` on the method, enabling bean definition overriding, or widening component scanning: the issue is **method overridability**, not whether the container can locate dependencies.

### 4.1. `private` in lite mode

When `proxyBeanMethods=false`, Spring does not need a subclass to intercept `@Bean` method calls. Thus Spring allows lite factory methods to use more flexible access modifiers, including `private`, provided the method can be invoked via reflection accordingly.

```java
@Configuration(proxyBeanMethods = false)
class LitePrivateConfig {

    @Bean
    private Engine engine() {
        return new Engine();
    }

    @Bean
    Car car(Engine engine) {
        return new Car(engine);
    }
}
```

This is **illustrative code** requiring `Engine`/`Car` classes. Spring can invoke `engine()` as a factory method to register the bean, while `car(Engine engine)` receives that exact bean through **parameter dependency resolution**. There is no need to call `engine()` from `car()`, so CGLIB inter-bean interception is unnecessary.

**Caution:** if a Java module runs under JPMS with `module-info.java`, Spring's reflective access to a private factory method can be restricted by module openness; configure `opens` in the right place. Simple examples using the ordinary classpath do not use a module descriptor.

### 4.2. `private @Bean` does not mean "private bean"

`private` is a Java method modifier, **not bean visibility**. A bean registered by Spring from a private factory method in lite mode can still be looked up from the same `ApplicationContext` if the bean definition is valid and scope permits:

```java
Engine engine = context.getBean(Engine.class);
```

This is an illustrative snippet with an initialized `context` variable. A private method does not hide the bean from the container or turn it into a private dependency under Java access control.

### 4.3. Package-private and protected in full mode

An instance `@Bean` method does not have to be `public` to be intercepted in full mode. Package-private or `protected` methods **can be overridden under Java rules** if they are not `final` and not blocked by other JVM/JPMS visibility constraints. Many Spring JavaConfig examples use package-private methods:

```java
@Configuration
class ValidPackagePrivateConfig {
    @Bean
    Engine engine() {
        return new Engine();
    }
}
```

Here `engine()` is not declared `public`, yet is neither `private` nor `final`; this differs from the two invalid examples above.

To reduce reflection/visibility risks in complex environments, infrastructure factory methods can intentionally be kept package-private or public. Do not change every method to public solely for Spring CGLIB if unnecessary.

## 5. `static`: Valid for Creating Beans, Yet Without Interception

### 5.1. Why doesn't CGLIB intercept static methods?

Java resolves `static` methods by class, not by instance virtual dispatch. CGLIB intercepts inter-bean calls in full `@Configuration` via **subclassing and method overriding**; a static method cannot be overridden like an instance method.

Example:

```java
@Configuration
class StaticBeanConfig {

    @Bean
    static Engine engine() {
        return new Engine();
    }

    @Bean
    Car car() {
        return new Car(engine()); // Direct Java static method call.
    }
}
```

This is illustrative code. Spring registers the **`engine` bean** from the static factory method. However, the `engine()` call from `car()` is a direct **static Java call**: it executes `new Engine()` again and can construct an object **outside** the managed `engine` singleton.

Therefore:

- `context.getBean(Engine.class)` returns the container-managed `engine` bean.
- `context.getBean(Car.class).engine()` can point to a **different** `Engine` object created by the static call inside `car()`.
- That happens even when `StaticBeanConfig` uses **full `@Configuration`**.
- Simply writing `@Bean` on a static method **does not mean** the factory method is unmanaged by Spring; the difference is between a **BeanFactory invocation** and a **direct Java call**.

### 5.2. Static `@Bean` does not mean "JVM-wide" singleton

The Java `static` keyword in `static @Bean` specifies that the method belongs to the class, **not the bean's scope**. Spring's default `singleton` scope remains **one instance per BeanFactory/container**:

- Two independent `ApplicationContext`s can hold two corresponding singleton instances.
- `@Scope("prototype")` on a static `@Bean` can still request a new object per scope when resolved by the container.
- A direct Java call to a static method always runs the method body with Java semantics; the container does not automatically turn it into a lookup.

Do not use static variables to hold a "system-wide singleton" and confuse them with Spring singletons. Across multiple applications/contexts or parallel tests, static state can leak data between tests and cause hard-to-reproduce bugs.

### 5.3. How to fix inter-bean references to a static `@Bean`

Replace:

```java
@Bean
Car car() {
    return new Car(engine()); // Direct static method call.
}
```

with:

```java
@Bean
Car car(Engine engine) {
    return new Car(engine);   // BeanFactory supplies Engine.
}
```

Both snippets are **illustrative alternatives** using the same `Car`/`Engine` classes from the example. Spring resolves the `Engine` parameter from the container before calling `car(...)`; this preserves the proper scope/managed reference and does not depend on whether the static method is intercepted.

This is a practical rule worth remembering: **passing dependencies via `@Bean` parameters** is far more consistent across full mode, lite mode, and dependencies produced by static factory methods.

## 6. Why Do Some Post-Processors Use `static @Bean`?

### 6.1. `BeanFactoryPostProcessor` participates very early

`BeanFactoryPostProcessor` (BFPP) processes metadata before most singletons are created. If a BFPP is produced by an **instance `@Bean` method**, BeanFactory must instantiate the configuration object early to invoke the method, which can happen before injection/lifecycle callbacks on the config object itself are complete. Static methods avoid that requirement:

```java
@Configuration
class InfraConfig {
    @Bean
    static PropertySourcesPlaceholderConfigurer placeholders() {
        return new PropertySourcesPlaceholderConfigurer();
    }
}
```

This is illustrative syntax requiring importing `org.springframework.context.support.PropertySourcesPlaceholderConfigurer`. Spring recommends static factories for BFPPs where appropriate because of their special initialization timing.

### 6.2. `BeanPostProcessor` also needs to be ready early

`BeanPostProcessor` (BPP) processes bean **instances** before/after initialization, potentially wrapping proxies or applying lifecycle callbacks. A non-static factory creating a BPP risks instantiating the config or dependencies too early; a static factory helps avoid part of that risk:

```java
@Configuration(proxyBeanMethods = false)
class InfrastructureConfiguration {
    @Bean
    static BeanPostProcessor auditPostProcessor() {
        return new BeanPostProcessor() {};
    }
}
```

The example requires importing `org.springframework.beans.factory.config.BeanPostProcessor`; the empty processor only illustrates the declaration and does **not** record audits. A real BPP must implement callbacks and manage ordering; the lesson on static `@Bean` and early type discovery covers this process in depth.

### 6.3. Trade-offs and limitations

A static factory is **not** intercepted by CGLIB on direct calls, cannot access configuration instance state, and does not make the bean a JVM-wide singleton. The method can still accept Spring-resolved dependencies; those dependencies themselves can trigger unexpected early initialization. Hence do not mark methods `static` wholesale, especially for ordinary business beans.

## 7. Runnable Java 17+ Example: Full, Lite, and Static

The example creates **four independent `ApplicationContext`s**, each comparing a container-managed `Part` bean with the `Part` received by a `Product`:

1. **FULL**: overridable instance methods; inter-bean call intercepted by CGLIB.
2. **LITE_DIRECT**: `final` configuration class, `private`/`final` factory methods; direct call executes as plain Java.
3. **LITE_PARAMETER**: `final` configuration class yet factory parameter receives managed dependency; no extra object.
4. **STATIC_DIRECT**: valid static `@Bean` in full configuration, yet direct static call is not intercepted by CGLIB.

The classes are registered one by one in **different contexts**, so there are no bean-name conflicts. The example uses JDK 17+ and Spring Framework 6.2.19.

### 7.1. Structure

```text
bean-method-modifiers-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── BeanMethodModifiersDemo.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'bean-method-modifiers-demo'
```

File `build.gradle`:

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
    mainClass = 'BeanMethodModifiersDemo'
}
```

Do not declare CGLIB separately: Spring Core includes a repackaged CGLIB version. Use a Gradle version compatible with JDK 17+.

### 7.2. Complete Java file

Create `src/main/java/BeanMethodModifiersDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class BeanMethodModifiersDemo {

    private static final AtomicInteger CREATED = new AtomicInteger();

    public record Part(int id) {
        public Part() {
            this(CREATED.incrementAndGet());
        }
    }

    public record Product(Part part) {
    }

    // Full mode: instance @Bean methods are all overridable.
    @Configuration
    public static class FullConfig {

        @Bean
        public Part part() {
            return new Part();
        }

        @Bean
        public Product product() {
            return new Product(part());
        }
    }

    // Lite: final configuration class and private/final factory methods.
    @Configuration(proxyBeanMethods = false)
    public static final class LiteDirectConfig {

        @Bean
        private Part part() {
            return new Part();
        }

        @Bean
        public final Product product() {
            return new Product(part());
        }
    }

    // Lite: modifiers stay the same, yet using method parameter DI.
    @Configuration(proxyBeanMethods = false)
    public static final class LiteParameterConfig {

        @Bean
        private Part part() {
            return new Part();
        }

        @Bean
        public final Product product(Part part) {
            return new Product(part);
        }
    }

    // Full configuration, yet static @Bean is not overridden.
    @Configuration
    public static class StaticDirectConfig {

        @Bean
        public static Part part() {
            return new Part();
        }

        @Bean
        public Product product() {
            return new Product(part());
        }
    }

    private static void inspect(
            String label, Class<?> configurationClass) {

        CREATED.set(0);

        try (var context =
                     new AnnotationConfigApplicationContext(configurationClass)) {

            Part managed = context.getBean(Part.class);
            Product product = context.getBean(Product.class);

            System.out.println("== " + label + " ==");
            System.out.println("samePart = " + (managed == product.part()));
            System.out.println("instances = " + CREATED.get());
        }
    }

    public static void main(String[] args) {
        inspect("FULL", FullConfig.class);
        inspect("LITE_DIRECT", LiteDirectConfig.class);
        inspect("LITE_PARAMETER", LiteParameterConfig.class);
        inspect("STATIC_DIRECT", StaticDirectConfig.class);
    }
}
```

`FullConfig` and `StaticDirectConfig` are not `final`; their instance `@Bean` methods are overridable. Both lite classes are marked `final` and intentionally contain `private`/`final` methods to demonstrate that CGLIB constraints **no longer apply for interception** when `proxyBeanMethods=false`.

`AtomicInteger` merely counts how many times the `new Part()` constructor is invoked. `CREATED.set(0)` runs before creating each context, and within each context `main` constructs/reads beans on a single thread. This keeps the count deterministic; never use a global counter like this as business state.

### 7.3. Run and stdout

In the project directory:

```bash
gradle run --quiet
```

If using the Gradle Wrapper on Linux/macOS:

```bash
./gradlew run --quiet
```

On Windows PowerShell:

```powershell
.\gradlew.bat run --quiet
```

The `System.out.println` lines printed by the program:

```text
== FULL ==
samePart = true
instances = 1
== LITE_DIRECT ==
samePart = false
instances = 2
== LITE_PARAMETER ==
samePart = true
instances = 1
== STATIC_DIRECT ==
samePart = false
instances = 2
```

This output applies to the simple program above, with default singletons and no other components/factories constructing `Part`. Gradle or logging systems may emit additional lines outside the program's `System.out.println` statements.

### 7.4. Explaining each case

**FULL:** Spring enhancement can intercept `product() -> part()`. Since `part` is a managed singleton bean, `product.part()` and `context.getBean(Part.class)` are the exact same object. Only one `Part` is created.

**LITE_DIRECT:** `LiteDirectConfig` is a `final` class, `part()` is `private`, and `product()` is `final`. BeanFactory calls them as factory methods in lite mode; when `product()` calls `part()`, that is an ordinary Java call. The context also creates a separate managed `part` singleton. Total two objects, identity `false`.

**LITE_PARAMETER:** No need to intercept `part()`; BeanFactory resolves the `Part part` parameter for `product(Part part)`. The factory receives the managed `part` singleton and keeps that reference—total one object even though the config class remains `final` and the factory methods `private`/`final`.

**STATIC_DIRECT:** `StaticDirectConfig.part()` is registered as a static factory method; the container creates one managed singleton. Yet inside `product()`, `part()` is a static Java call not overridden by CGLIB, creating another object. Total two objects, identity `false`. The configuration class not being `final` does not remove the static dispatch limitation.

### 7.5. Why didn't the example put the invalid configurations in `main`?

The examples in section 8 intentionally violate full configuration constraints. Registering them alongside valid configurations would cause the context to fail right at the parsing/enhancement phase, producing no stdout for comparison. Isolating error cases as separate illustrations helps learners see how **startup errors** differ from **identity errors caused by direct calls**.

## 8. Intentionally Invalid Configuration Examples in Full Mode

Do not put the snippets in this section into the complete program from section 7. They are **deliberate inputs for testing Spring error messages**, not configurations to deploy.

### 8.1. `final @Configuration` class

```java
@Configuration
final class BadFinalConfiguration {
    @Bean
    Part part() {
        return new Part();
    }
}
```

When processing full mode, Spring needs to create a CGLIB subclass, yet `BadFinalConfiguration` cannot be extended. Fix: remove `final` or choose lite mode with parameter DI.

### 8.2. `final` instance `@Bean` method

```java
@Configuration
class BadFinalMethodConfiguration {
    @Bean
    final Part part() {
        return new Part();
    }
}
```

`part()` is `final` and therefore cannot be overridden by a subclass. Even with just one bean definition, this still fails full-mode configuration validation, regardless of whether any inter-bean call currently exists.

### 8.3. `private` instance `@Bean` method

```java
@Configuration
class BadPrivateMethodConfiguration {
    @Bean
    private Part part() {
        return new Part();
    }
}
```

Spring full mode cannot override a private instance method to provide bean lookup semantics. If switching to lite, a private factory method is allowed, yet pay attention to reflective access/JPMS and avoid direct calls when you want a reference to the managed bean.

### 8.4. Does static `@Bean` automatically throw an error like final/private?

**No.** Spring supports static factory methods in configuration classes, including full configuration. What you must understand is that **static calls are not intercepted**. Thus bugs typically manifest as **unexpected instance count/identity/lifecycle**, not because `static @Bean` syntax is forbidden by Spring.

| Declaration | Full `@Configuration` | Lite mode |
| --- | --- | --- |
| `final class Config` | Invalid because subclassing is needed | Allowed |
| `@Bean final T bean()` (instance) | Invalid because not overridable | Allowed |
| `@Bean private T bean()` (instance) | Invalid because not overridable | Allowed |
| `@Bean static T bean()` | Valid, yet direct calls are not intercepted | Valid, ordinary Java direct calls |
| `@Bean T bean()` (package-private, overridable) | Valid when visibility/overridability fit | Valid |
| `@Bean T bean(Dependency dependency)` | Spring resolves parameter | Spring resolves parameter |

## 9. Misconceptions to Avoid

### 9.1. "If the `@Bean` method is private, the bean is also private"

False. The `private` modifier governs Java method accessibility; it does not create a "private bean" in Spring. If the method is accepted by Spring (e.g., lite configuration on an ordinary classpath), the bean has a name and scope like any other bean and can be looked up from the container.

### 9.2. "Static `@Bean` = application-wide Spring singleton"

False. Java `static` and Spring `singleton` belong to two different concepts. A Spring singleton is normally scoped to **one container**, whereas a static method belongs to a Java class. A Spring singleton bean created from a static factory method can still differ between two contexts.

### 9.3. "Switching to lite mode means Spring stops doing DI"

False. Lite mode still registers `@Bean`s and resolves factory method parameters. Use `@Bean Product product(Part part)` to receive dependencies from BeanFactory instead of calling `part()` yourself.

### 9.4. "Simply calling `new Config()` gets interception"

False. An object from `new Config()` outside Spring is a plain Java object, not the Spring-enhanced configuration instance. Calling `new Config().product()` yourself does not guarantee Spring-managed singleton semantics. Similarly, static direct calls cannot be intercepted just because they sit inside a `@Configuration`-annotated class.

### 9.5. "Every `final` method on a configuration class is forbidden"

Inaccurate. The full-mode rule focuses on **instance `@Bean` factory methods that need overriding**; another Java helper method without `@Bean` is not subject to inter-bean reference interception under the same rule. Even so, full configuration class design should avoid confusing inheritance/visibility tricks.

### 9.6. "CGLIB enhancement of `@Configuration` IS Spring AOP"

Not quite. Both mechanisms can use CGLIB subclassing, yet their goals differ:

- Full configuration enhancement intercepts **`@Bean` method calls** to preserve BeanFactory semantics.
- Spring AOP intercepts **calls to business beans** via proxies for concerns like transactions, caching, and security when configured.

In proxy-based AOP, **self-invocation** on the target usually bypasses the proxy. Do not deduce AOP self-invocation rules from full `@Configuration` examples.

### 9.7. "Static factory methods cannot receive dependencies"

Incorrect. Spring can still resolve parameters of a static `@Bean` method via BeanFactory, e.g., `@Bean static Service service(Repository repository)` when a suitable `Repository` bean exists. Still, for early-initialized BFPP/BPPs, overly complex dependencies can trigger early creation of other beans and disrupt post-processing.

### 9.8. "Removing `final` always eliminates all errors"

Not necessarily. A non-final class can still fail if instance `@Bean` methods are private/final, bean candidates are missing, circular dependencies cannot be resolved, module reflection is restricted, or the factory method itself throws an exception. Distinguish enhancement/validation errors from autowiring/bean-creation errors.

## 10. Distinguishing Validation, DI, and Lifecycle Errors

| Symptom | Possible Cause | Investigation Direction |
| --- | --- | --- |
| Context fails early while processing full config | Final config class or private/final instance `@Bean` method | Check `proxyBeanMethods`, access modifiers, nested classes |
| Context refreshes fine yet object count increases | Lite direct calls, static direct calls, or prototype bean scope | Trace `otherBean()` callers; compare against managed `getBean(...)` |
| `BeanCreationException` on another bean | Factory method logic error, missing dependency, or circular dependency | Read root cause; inspect `@Bean` signature and DI graph |
| `UnsatisfiedDependencyException` | Missing or ambiguous dependency | Check bean definitions, types, qualifiers, profiles |
| An object misses AOP/lifecycle processing | Created by direct Java call outside BeanFactory | Switch to container lookup/parameter injection |
| `@Value`/`@Autowired` on config not populated | A non-static BFPP/BPP forced config instantiation too early | Consider a static factory for the post-processor |
| JPMS `InaccessibleObjectException` | Module did not open package needed for reflection/enhancement | Check module descriptor and `opens` |
| Tests with `new Config()` do not match the app | No Spring-enhanced managed configuration instance | Use `AnnotationConfigApplicationContext` in integration tests |

### 10.1. Quick check with a real context

Given `FullConfig` and `Product`/`Part` from section 7:

```java
try (var context =
        new AnnotationConfigApplicationContext(FullConfig.class)) {
    Part managed = context.getBean(Part.class);
    Product product = context.getBean(Product.class);
    System.out.println(managed == product.part());
}
```

This is an **illustrative** snippet using the classes from the complete program; it does not run as a standalone `.java` file. With full mode and singletons, the output is `true`. Try switching the configuration to lite direct and repeating the check to observe `false`.

**Note:** inspecting class names like `$$SpringCGLIB$$...` is only peeking at an implementation detail. Do not write business logic depending on dynamically generated class name fragments; test behavior via bean identity, scope, and DI semantics.

## 11. Exercises with Answers

### Exercise 1 — Final configuration class

Given `@Configuration final class FinalConfig` with a regular instance `@Bean` method. Is it valid in full mode?

**Answer:** No, because full mode needs to generate a CGLIB subclass. Remove `final` or use `@Configuration(proxyBeanMethods=false)` with independent factory methods/proper DI.

### Exercise 2 — Private method

Can `@Bean private Part part()` be overridden by a subclass in full mode?

**Answer:** No; private instance methods are not overridable. In lite mode, a factory method can be private and invoked by the container via reflection when the environment permits.

### Exercise 3 — Final method

The `@Configuration` class is not final, yet the method is `@Bean final Product product()`. Is Spring full mode happy with this?

**Answer:** No; the restriction applies to factory methods as well. Removing `final` from the class alone does not fix it if the method remains `final`.

### Exercise 4 — Static factory

`@Configuration` has `@Bean static Part part()`, and `@Bean Product product()` calls `part()` directly. Is that call intercepted by CGLIB to return the managed singleton?

**Answer:** No. A static call is an ordinary Java call. To get the managed `Part`, declare `@Bean Product product(Part part)`.

### Exercise 5 — Static and early lifecycle

Why is `@Bean static PropertySourcesPlaceholderConfigurer placeholders()` commonly recommended?

**Answer:** Because the factory creating the BFPP can be invoked early **without instantiating the enclosing configuration class**, reducing the risk that injection/lifecycle annotations on the config are not yet fully processed.

### Exercise 6 — Two contexts

Two separate `ApplicationContext`s each register a singleton bean from `@Bean static Part part()`. Must they return the exact same `Part` instance shared across the whole JVM?

**Answer:** No. Spring singletons are per container; `static` is only a property of the method. If code adds its own static cache, that is custom logic rather than Spring's default.

### Exercise 7 — Final lite class with proper injection

`@Configuration(proxyBeanMethods=false) final class Config` has `@Bean private Part part()` and `@Bean final Product product(Part part)`. Is CGLIB enhancement needed to share the `Part` singleton?

**Answer:** No. BeanFactory resolves the parameter from the container. This behavior is verified in the `LITE_PARAMETER` case in section 7.

### Exercise 8 — Prototype scope

If the `Part` bean has prototype scope, is `FULL` guaranteed to create only one instance?

**Answer:** No. Full inter-bean calls preserve the container's **scope semantics**, and prototypes do not share a single instance like singletons. The counting example in section 7 assumes default singletons.

### Exercise 9 — Changing proxy mode to fix missing beans

A factory method needs `Repository` yet the context has no bean of that type. Does enabling `proxyBeanMethods=true` automatically create `Repository`?

**Answer:** No. That is a dependency resolution error requiring registering the bean or fixing qualifiers/configuration; enhancement does not conjure an undefined dependency.

### Exercise 10 — Full configuration and `@Transactional`

If `@Bean` inter-bean calls are intercepted by CGLIB, does `this.transfer()` on a Spring AOP service automatically start a transaction?

**Answer:** You cannot infer that. CGLIB configuration enhancement and AOP proxying are two different mechanisms; self-invocation on an AOP target normally bypasses the proxy.

## 12. Checklist Before Choosing Modifiers and Proxy Mode

- Is the class a **full `@Configuration`**? Is `proxyBeanMethods` defaulting to `true`?
- Is the full config class `final`? Are nested configs declared `static` when appropriate?
- Are **instance `@Bean` factory methods** `private` or `final`?
- Is any `static @Bean` method **called directly** from another `@Bean` method?
- When managed dependencies are needed, are **factory-method parameters** used instead of direct calls?
- Are there BFPP/BPPs needing early initialization, and should their factory methods be `static`?
- Is the bean scope singleton? Are prototype, request, session, lazy, or AOP proxies involved?
- Is any object constructed with `new` outside BeanFactory while being assumed to be a managed bean?
- Has a real Spring context been created to verify registration/identity/lifecycle?
- If using Java modules, are packages opened appropriately for reflection/proxying?

## 13. Summary

**Limitations of full `@Configuration` stem from intercepting inter-bean method calls via a CGLIB subclass**: `final` classes cannot be subclassed, and `final` or `private` instance methods cannot be overridden. Hence those declarations are unsuitable in full mode. `@Configuration(proxyBeanMethods=false)` removes the need for that interception, allowing classes/methods with those modifiers in lite mode as long as the method is a valid factory and the container can invoke it.

**`static @Bean` is valid in Spring**, yet direct calls to a static method are never intercepted in any mode. It is especially useful for creating infrastructure beans such as `BeanFactoryPostProcessor` and `BeanPostProcessor` early without instantiating the configuration class. The flip side is that direct static calls can construct objects outside the managed singleton.

**The style least dependent on proxy mode** expresses dependencies through factory method parameters:

```java
@Bean
Product product(Part part) {
    return new Product(part);
}
```

Then Spring resolves `Part` from BeanFactory whether the `part` bean was created by an instance factory method or a static factory method, and whether the configuration class uses full or lite mode.

### Official Documentation

- [Spring Framework 6.2 — `@Bean` Javadoc: Full mode, Lite mode, and static post-processors](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/Bean.html).
- [Spring Framework 6.2 — `@Configuration` Javadoc: `proxyBeanMethods` and constraints](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/Configuration.html).
- [Spring Framework Reference — Basic Concepts: `@Bean` and `@Configuration`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/basic-concepts.html).
- [Spring Framework Reference — Using `@Bean`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html).
- [Spring Framework Reference — Composing Java-based Configurations](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html).
