# Full `@Configuration` Mode and CGLIB Enhancement in Spring Framework

## 1. The Question: Does Calling a `@Bean` Method Always Create a New Object?

Look at a Java configuration class:

```java
@Configuration
class ApplicationConfig {

    @Bean
    Engine engine() {
        return new Engine();
    }

    @Bean
    Vehicle car() {
        return new Vehicle(engine());
    }

    @Bean
    Vehicle truck() {
        return new Vehicle(engine());
    }
}
```

This is an **illustrative snippet**; `Engine` and `Vehicle` are undeclared application classes. In plain Java, the two `engine()` calls inside `car()` and `truck()` would execute the method body twice and create two separate `new Engine()` objects. Yet when `ApplicationConfig` is processed by Spring as a **full `@Configuration` (full mode)** class, calls between `@Bean` methods are intercepted: Spring can redirect them to the BeanFactory, so both `car` and `truck` receive the **singleton `engine` bean**.

That mechanism is **CGLIB enhancement**: Spring generates a runtime subclass of the configuration class and intercepts eligible calls to `@Bean` methods. This is the behavior enabled by default via:

```java
@Configuration(proxyBeanMethods = true)
```

Normally you only write `@Configuration` because `proxyBeanMethods` defaults to `true`.

However, when changed to:

```java
@Configuration(proxyBeanMethods = false)
```

Spring **does not enhance `@Bean` methods to intercept direct calls**. Calling `engine()` from `car()` is an ordinary Java call that can create an extra object **other than** the `engine` singleton bean registered by the container. Both modes allow Spring to process `@Bean` and register beans; the difference lies in **Java method call semantics**, not whether `@Bean` still works.

This lesson focuses on:

- Full `@Configuration`, the dynamically generated CGLIB subclass, and calls between `@Bean` methods;
- singleton/scope, lifecycle, and AOP semantics when referencing beans via methods;
- limitations of full mode (`final`, `private`, `static` classes/methods) compared to lite mode;
- choosing `proxyBeanMethods=false` and dependency injection via `@Bean` parameters;
- how not to confuse configuration enhancement with Spring AOP proxies;
- a runnable Java 17+ example with Spring Context, stdout analysis, common errors, and exercises.

## 2. `@Configuration` Is a Source of Bean Definitions

`@Configuration` belongs to the `org.springframework.context.annotation` package. It marks a class containing Java configuration metadata, typically via `@Bean`-annotated methods:

```java
@Configuration
public class BillingConfiguration {

    @Bean
    PaymentClient paymentClient() {
        return new PaymentClient("local");
    }
}
```

This snippet is illustrative and does not run standalone without the `PaymentClient` class. Spring needs to learn about `BillingConfiguration` via direct registration, component scanning, `@Import`, or another configuration mechanism. The mere presence of the annotation in source code does not start a container on its own.

When the configuration is processed, Spring registers **bean definitions** from `@Bean` methods. The container then creates objects when needed according to scope, dependencies, lazy flags, and the refresh process. By default, a `@Bean`'s scope is **singleton per BeanFactory**.

Key distinction:

1. Spring invokes a `@Bean` factory method when creating a managed bean.
2. Application code **itself calls** a `@Bean` method on a configuration object.

In full mode, a type-2 call on the **Spring-enhanced and managed configuration object** can be converted into a container lookup; in lite mode that call remains plain Java. That is precisely why `proxyBeanMethods` exists.

## 3. How Does Full Mode Work?

### 3.1. The enhanced subclass

Suppose a configuration class is named `DemoConfig`. When processing full mode, Spring can generate a runtime type with an inheritance relationship like:

```text
                DemoConfig
                    ^
                    |
          DemoConfig$$SpringCGLIB$$...
                    |
                    v
        Configuration bean in Spring
```

The generated class name is an **implementation detail** and should never be hard-coded, parsed, or relied upon as an API. Spring uses CGLIB repackaged inside the `spring-core` module (`org.springframework.cglib` namespace), so no separate CGLIB dependency is needed in typical Spring Context examples.

To visualize the mechanism, pseudocode that is **not actual Spring source code**:

```java
// Pseudocode explaining the idea; DOES NOT run standalone.
@Override
Engine engine() {
    if (thisCallIsBeingUsedByBeanFactoryToCreateEngine()) {
        return super.engine(); // Real factory body constructs the bean.
    }
    return beanFactory.getBean("engine", Engine.class);
}
```

The interceptor's goal is to distinguish **a call the BeanFactory is making to instantiate the bean** from **a call referencing an already-managed bean**. If every call simply bounced back to the BeanFactory indiscriminately, a factory currently constructing that bean would recurse. The actual mechanism also handles scoping, bean state, type metadata, and special cases.

### 3.2. Singleton creation and inter-bean call flow

```text
Spring registers:
  "engine" -> DemoConfig.engine()
  "car"    -> DemoConfig.car()
  "truck"  -> DemoConfig.truck()

When Spring creates "car":
  BeanFactory calls factory car()
    |
    v
  Car factory calls engine()
    |
    v
  CGLIB interceptor checks "engine"
    |
    +-- Managed singleton already exists? -> reuse existing bean
    |
    +-- Not yet? -> ask BeanFactory to create/get "engine"
    |
    v
  car receives Engine reference managed by Spring

When Spring creates "truck":
  truck factory calls engine()
    |
    v
  CGLIB redirects to the same singleton "engine"
```

This diagram shows **semantics for default singletons**, not the full internal state machine. The key result is `car.engine() == truck.engine()` **and** both equal `context.getBean(Engine.class)` when properly configured.

### 3.3. Full mode is not generic caching of all calls

CGLIB enhancement honors **bean scope** and container semantics, rather than blindly caching every Java method return value.

- `singleton`: for normal references, the same managed instance is reused within one container.
- `prototype`: BeanFactory creates an instance per resolution; an inter-bean call can receive a new prototype.
- web/custom scope: the result depends on the active scope and bean availability in that context.
- if the BeanFactory creates an AOP proxy or scoped proxy for the bean, cross-method lookup can receive the **container-exposed reference**, not necessarily the raw object constructed directly with `new` inside the factory.

Therefore, do not think of full mode as "every `@Bean` method executes strictly once" in every scope. That statement only matches ordinary singletons when nothing else invokes the factory through another mechanism.

## 4. Calls That Are and Are Not Intercepted

| Scenario | Full `@Configuration` (`proxyBeanMethods=true`) | `proxyBeanMethods=false` / lite |
| --- | --- | --- |
| BeanFactory calls method to create bean | Method runs to build managed instance | Method runs to build managed instance |
| `car()` calls `engine()` in same config | Inter-bean call intercepted if eligible; returns BeanFactory reference | Plain Java call; may `new Engine()` again |
| `context.getBean("engine")` | Returns managed bean per scope | Returns managed bean per scope |
| `config.engine()` on Spring-managed configuration bean | Can be intercepted to return bean from container | Runs plain Java method |
| `new Config().engine()` outside Spring | No container-created interceptor | Runs plain Java |
| Bean declared with `@Bean` has singleton scope | Yes | Yes |
| Constructor/method parameter injection | Yes | Yes |
| Configuration class can be `final` | No in full mode because subclassing is required | Possible, if no other constraints apply |
| Interception across `static @Bean` methods | Does not apply via virtual override | Does not apply |
| CGLIB subclass created for bean method interception | Yes | Not needed for this purpose |

**Do not say `proxyBeanMethods=false` disables Spring bean management.** It only disables **proxying of `@Bean` methods** on the configuration class. Bean definitions, dependency resolution, and lifecycle are still managed by Spring as usual.

### 4.1. Calls from another config

If a bean is accessed via a **managed instance of a full configuration class**, a `@Bean` method call can be redirected by the interceptor into a container lookup even when called from elsewhere. However, passing dependencies directly into `@Bean` methods or constructors remains easier to trace and creates less coupling between configuration classes.

Do not treat a configuration bean as a **service locator** and call `config.someBean()` throughout the application: that couples business code to the configuration class and its proxy mode.

### 4.2. How self-invocation differs from Spring AOP

A very common misconception: "Spring AOP proxies don't intercept self-invocation; why is `car()` calling `engine()` intercepted?"

The two mechanisms are not the same:

- **CGLIB enhancement of full `@Configuration`**: Spring generates a subclass of the configuration class to intercept `@Bean` method calls, including inter-bean calls occurring in eligible configuration code.
- **Spring AOP** with `@Transactional`, `@Cacheable`, etc.: is usually a separate proxy wrapping the target bean. When a target method calls another method on itself via `this`, self-invocation normally bypasses the AOP proxy.

You cannot infer Spring AOP semantics from `@Bean` interception. Full configuration does not automatically enable transactions, caching, or HTTP handling.

## 5. Lite Configuration: When and Why to Use `proxyBeanMethods=false`?

Since Spring Framework 5.2, `@Configuration` provides the option:

```java
@Configuration(proxyBeanMethods = false)
public class SimpleConfiguration {
    @Bean
    Formatter formatter() {
        return new Formatter();
    }
}
```

In this configuration, Spring still discovers `formatter()` and can create the singleton bean `formatter`. Yet the method is **not overridden to perform inter-bean interception**.

When factory methods are **independent** and do not make Java `someBean()` calls to other `@Bean` methods, proxying brings little value. Disabling interception:

- removes the need to generate a CGLIB subclass for intercepting `@Bean` methods;
- removes the corresponding subclassing restrictions on the configuration class/methods;
- may reduce some initial configuration overhead, though it **does not guarantee** dramatically faster startup for every application;
- keeps Java call semantics straightforward: calling a method means running the method body.

A recommended example:

```java
@Configuration(proxyBeanMethods = false)
class AppConfig {

    @Bean
    Engine engine() {
        return new Engine();
    }

    @Bean
    Vehicle car(Engine engine) {
        return new Vehicle(engine);
    }

    @Bean
    Vehicle truck(Engine engine) {
        return new Vehicle(engine);
    }
}
```

This is an **illustrative snippet** requiring `Engine`/`Vehicle` classes. The BeanFactory **resolves `Engine` as a parameter** before calling `car(...)`/`truck(...)`, so both receive the same managed singleton without calling `engine()` via CGLIB.

### 5.1. Lite mode is not only `@Configuration(proxyBeanMethods=false)`

By Spring convention, `@Bean` methods declared inside classes **not marked with full `@Configuration`**, such as a `@Component` class, also have "lite" semantics when processed. Those methods are factory methods used by the container; inter-bean calls are **not** guaranteed to go through the container.

```java
@Component
class UtilityFactories {

    @Bean
    Formatter formatter() {
        return new Formatter();
    }

    @Bean
    Printer printer() {
        return new Printer(formatter()); // Plain Java call.
    }
}
```

This is **illustrative** code requiring `Formatter`/`Printer` and scanning. To avoid objects outside the managed lifecycle, write `printer(Formatter formatter)` and call `new Printer(formatter)`.

When a class containing `@Bean` methods carries both `@Component` and `@Configuration`, configuration-processing semantics must be determined from the actual annotations; do not guess merely from the class name.

## 6. Constraints of Full Mode and CGLIB

CGLIB enhances classes by generating a subclass and overriding eligible methods. Java inheritance and overriding rules are therefore critical.

### 6.1. Configuration classes cannot be `final` in full mode

Incorrect example:

```java
@Configuration
public final class FinalConfig {
    @Bean
    Engine engine() {
        return new Engine();
    }
}
```

This is a **configuration error example**, not a standalone runnable file. Java `final` blocks inheritance, so Spring cannot generate a subclass for CGLIB enhancement. In full mode, the configuration class must be subclassable. Either make the class non-`final` or use `@Configuration(proxyBeanMethods=false)` if inter-bean interception is not needed.

### 6.2. `@Bean` methods in full mode must be overridable

Unsuitable example:

```java
@Configuration
class InvalidConfig {

    @Bean
    private Engine engine() {
        return new Engine();
    }

    @Bean
    public final Vehicle car() {
        return new Vehicle(engine());
    }
}
```

This is an **error example**; do not copy it into a runnable project. `private` methods cannot be overridden; `final` methods cannot be overridden. Full-mode `@Bean` methods must meet these constraints so Spring can intercept them. Use appropriate access modifiers and remove `final`, or switch to lite configuration with independent factory methods.

### 6.3. Static `@Bean` methods are a separate case

`static` methods belong to the class and lack instance-based virtual dispatch; CGLIB cannot override them in the same way. Spring supports static `@Bean` factory methods for valid cases, especially infrastructure beans that must be declared static to initialize in the right phase.

**Do not assume calling `staticBeanMethod()` from Java code will be intercepted by the full configuration proxy to return a managed singleton.** If another bean needs the dependency created by a static method, pass it as a factory method parameter of the consuming bean.

A static `@Bean` method is appropriate when registering infrastructure like `BeanFactoryPostProcessor` in certain scenarios, yet that does not mean every factory method should be static.

### 6.4. `private` constructors and Java modules

Dynamic subclassing is also affected by visibility, class loaders, and the **Java Platform Module System** when using the module path. Do not lump every `InaccessibleObjectException` into a "missing bean" error. If JPMS blocks reflection/enhancement, check the `exports`/`opens` required for Spring.

Spring supports various forms of constructor injection into configuration classes, so a **public no-arg constructor is not mandatory** just to use full `@Configuration`. Constructor dependencies, if present, must be resolvable by the container like other beans.

### 6.5. Avoid relying on CGLIB internals

Do not parse `$$SpringCGLIB$$` from class names to drive business logic; generated class names can vary across versions or environments. Do not use Java reflection against internally generated method names. Verify behavior via managed bean identity, scopes, and dependency contracts.

## 7. Complete Java 17+ Example: Three Configuration Styles

The example uses **Spring Framework 6.2.19**, needing only `spring-context`. We create **three separate ApplicationContexts**:

1. **FULL**: default `@Configuration`, `@Bean` methods calling each other directly; all `Engine` references point to the same singleton.
2. **LITE_DIRECT**: `proxyBeanMethods=false` while still calling `engine()` directly; creates extra `Engine` objects outside the bean factory.
3. **LITE_PARAMETER**: `proxyBeanMethods=false` and passing `Engine` via factory method parameters; returns to sharing the single managed bean.

### 7.1. File layout

```text
spring-config-cglib-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── ConfigurationModesDemo.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'spring-config-cglib-demo'
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
    mainClass = 'ConfigurationModesDemo'
}
```

Use JDK 17+ and a JDK-compatible Gradle version. No separate `cglib` dependency is needed; CGLIB is repackaged inside `spring-core`, a dependency of Spring Context.

### 7.2. Complete Java source

Save `src/main/java/ConfigurationModesDemo.java`:

```java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class ConfigurationModesDemo {

    public static final class Engine {
        private static int constructions;

        public Engine() {
            constructions++;
        }

        public static void resetCount() {
            constructions = 0;
        }

        public static int created() {
            return constructions;
        }
    }

    public record Vehicle(Engine engine) {
    }

    // Full configuration: @Configuration has proxyBeanMethods = true.
    @Configuration
    public static class FullConfig {

        @Bean
        public Engine engine() {
            return new Engine();
        }

        @Bean
        public Vehicle car() {
            return new Vehicle(engine());
        }

        @Bean
        public Vehicle truck() {
            return new Vehicle(engine());
        }
    }

    // Lite: methods call one another as ordinary Java.
    @Configuration(proxyBeanMethods = false)
    public static class LiteDirectConfig {

        @Bean
        public Engine engine() {
            return new Engine();
        }

        @Bean
        public Vehicle car() {
            return new Vehicle(engine());
        }

        @Bean
        public Vehicle truck() {
            return new Vehicle(engine());
        }
    }

    // Lite, but using Spring DI via @Bean parameters.
    @Configuration(proxyBeanMethods = false)
    public static class LiteParameterConfig {

        @Bean
        public Engine engine() {
            return new Engine();
        }

        @Bean
        public Vehicle car(Engine engine) {
            return new Vehicle(engine);
        }

        @Bean
        public Vehicle truck(Engine engine) {
            return new Vehicle(engine);
        }
    }

    private static void inspect(
            String label, Class<?> configurationClass) {

        Engine.resetCount();
        try (var context =
                new AnnotationConfigApplicationContext(configurationClass)) {
            Engine managed = context.getBean(Engine.class);
            Vehicle car = context.getBean("car", Vehicle.class);
            Vehicle truck = context.getBean("truck", Vehicle.class);

            System.out.println("== " + label + " ==");
            System.out.println("managed==car: " +
                    (managed == car.engine()));
            System.out.println("managed==truck: " +
                    (managed == truck.engine()));
            System.out.println("car==truck: " +
                    (car.engine() == truck.engine()));
            System.out.println("enginesCreated: " + Engine.created());
        }
    }

    public static void main(String[] args) {
        inspect("FULL", FullConfig.class);
        inspect("LITE_DIRECT", LiteDirectConfig.class);
        inspect("LITE_PARAMETER", LiteParameterConfig.class);
    }
}
```

This is a valid Java file: only `ConfigurationModesDemo` is a top-level public class; the three configuration classes, `Engine`, and record `Vehicle` are nested public static classes. The `@Bean` methods are named `engine`, `car`, and `truck` and registered separately in each context.

`Engine.constructions` is an educational counter; the example runs on a single thread. In concurrent systems, real counters should use thread-safe utilities if measuring object creations. We reset the counter **before creating each context**; each `inspect` call closes the previous context before starting the next run.

### 7.3. Run command

From the project root directory:

```bash
gradle run --quiet
```

If using the Gradle Wrapper:

```bash
./gradlew run --quiet
```

On Windows PowerShell:

```powershell
.\gradlew.bat run --quiet
```

Lines printed by the program:

```text
== FULL ==
managed==car: true
managed==truck: true
car==truck: true
enginesCreated: 1
== LITE_DIRECT ==
managed==car: false
managed==truck: false
car==truck: false
enginesCreated: 3
== LITE_PARAMETER ==
managed==car: true
managed==truck: true
car==truck: true
enginesCreated: 1
```

This is stdout from `System.out.println`. If the environment configures additional logging, Gradle may display other output not belonging to the lines above.

### 7.4. Why does FULL create exactly one Engine?

`FullConfig` carries default `@Configuration`, so Spring processes it in full mode, enhancing it with CGLIB. With singleton `engine`:

- BeanFactory creates the managed `engine` once.
- `car()` calls `engine()` through the enhanced configuration object; the interceptor returns the managed bean reference.
- `truck()` also receives the same managed reference.
- `getBean(Engine.class)` returns that same bean.

Therefore all three `==` identity comparisons are `true`, and `new Engine()` runs exactly **once in the FULL context**.

### 7.5. Why does LITE_DIRECT create three Engines?

`LiteDirectConfig` disables interception. The container still creates one managed singleton `engine`, yet:

- `car()` performs a plain Java `engine()` call -> a new `Engine` **that is not the managed `engine` singleton**.
- `truck()` performs a plain Java `engine()` call -> another `Engine`.
- BeanFactory still retains its own `engine` singleton per the bean definition, because `engine` is declared as `@Bean` and non-lazy.

In total, **three `Engine` objects** are constructed in this context. `car`, `truck`, and the managed bean hold three distinct references, so all three `==` comparisons are `false`.

Notably, both `Vehicle`s are still **Spring beans** because BeanFactory creates them from `@Bean` factory methods. Only the `Engine` objects constructed by direct Java calls inside those two factory methods are separate objects rather than the singleton `engine` instance from BeanFactory.

### 7.6. Why does LITE_PARAMETER create only one Engine?

`LiteParameterConfig` uses no direct inter-bean calls. Spring resolves the `Engine` dependency before calling `car(Engine engine)` and `truck(Engine engine)`, passing the same managed singleton. No CGLIB subclass is needed for `@Bean` method interception. Thus bean behavior matches FULL in the example while dependency declaration remains explicit.

This is the key recommendation in modern applications: **if you choose `proxyBeanMethods=false`, pass bean dependencies via `@Bean` parameters instead of calling `@Bean` methods directly.**

### 7.7. Why does the example use three contexts?

Each context registers its own `engine`/`car`/`truck` bean names; mixing all three configs into one context would cause duplicate names and different semantics. Separating contexts isolates a single variable: interception and how dependencies are expressed.

All three contexts use singleton scopes. The example intentionally avoids prototypes so that scope-driven object creation does not obscure the comparison.

## 8. `@Bean` Parameters vs. Inter-Bean Calls: Which to Choose?

| Criterion | Full `@Configuration` + direct call | `proxyBeanMethods=false` + parameter |
| --- | --- | --- |
| Syntax | `return new Car(engine());` | `Car car(Engine engine) { return new Car(engine); }` |
| Who resolves bean dependency | CGLIB interceptor delegates to BeanFactory | BeanFactory resolves method argument |
| Needs CGLIB enhancement on config | Yes | No |
| `final` restriction on config | Yes | Not due to bean method interception |
| Dependencies readable from signature | Less explicit than parameters | Very explicit |
| Works in lite mode | No singleton/managed lookup guarantee with direct calls | Yes |
| Moving factory method to another config | May require changing the call | Usually lower coupling |
| AOP/scoped bean semantics | BeanFactory guarantees via lookup | BeanFactory guarantees when resolving argument |
| Risk of errors from calling method directly | Protected if full mode is processed properly | Avoided altogether when consistently using parameters |

There is no rule that "full mode is always bad" or "lite mode is always good": full mode is valuable when a configuration intentionally uses inter-bean references through Java methods. When that characteristic is not needed, lite mode with method-parameter injection is usually simpler and avoids subclassing constraints.

### 8.1. Notes on `@Bean` methods in another config

With two configuration classes, calling `otherConfig.engine()` can depend on whether `otherConfig` is an enhanced managed bean or just an ordinary Java object. Instead of wiring the configuration class itself into a service or another configuration, pass `Engine` directly into the consuming factory method.

```java
@Configuration(proxyBeanMethods = false)
class FeatureConfig {

    @Bean
    FeatureService featureService(Engine engine) {
        return new FeatureService(engine);
    }
}
```

This snippet is **illustrative only**: `FeatureService` must be defined and an `Engine` bean must exist in the context.

## 9. Scope, `@Lazy`, and Cases Where Counting Constructors Isn't Enough

### 9.1. Prototype: creating new instances is by design

If `engine` has `@Scope("prototype")`, every normal prototype lookup by the container creates a new instance. Full `@Configuration` when performing inter-bean calls through BeanFactory must also respect prototype scope; the goal is not to force a single object on every caller.

Meanwhile, a singleton `Car` receiving a prototype `Engine` via a factory method parameter normally keeps **the single prototype resolved when `Car` was constructed**. To obtain a fresh `Engine` per business operation, design `Car` to accept `ObjectProvider<Engine>` and call `getObject()` as needed.

### 9.2. Lazy: deferring bean creation

`@Lazy` on a bean definition can prevent pre-instantiating an unrequired singleton during context refresh. However, if another singleton being instantiated needs that bean, it may still have to be created. Full mode intercepting inter-bean references through BeanFactory does not mean every bean is always eager; lite mode does not mean every bean is always lazy.

### 9.3. AOP proxies and lifecycle

When BeanFactory applies `BeanPostProcessor`s to create an AOP proxy, the container can expose a proxy reference instead of the raw instance. Inter-bean lookup through full config preserves BeanFactory semantics, which matters for beans configured with transaction/security/caching aspects.

Do not call `new Service()` or direct lite `@Bean` methods and assume the object is the same managed bean; objects created outside the container are not automatically injected, proxied, initialized, or destroyed under the same managed lifecycle.

### 9.4. `FactoryBean` is a separate mechanism

Spring has the `FactoryBean<T>` interface for producing container-managed objects under factory-specific rules. A `@Bean` method returning a `FactoryBean` has special lookup/production semantics. That does not mean CGLIB enhancement simply caches raw return values. When working with `FactoryBean`, learn the distinction between the factory bean and the product object it creates.

## 10. Common Errors and How to Diagnose Them

| Symptom | Cause | Fix |
| --- | --- | --- |
| `@Configuration` class is `final` and context throws error | Full mode requires CGLIB subclassing | Remove `final` or use `proxyBeanMethods=false` when interception is unneeded |
| `@Bean` method is `private`/`final` | Cannot be overridden in full mode | Use overridable methods or lite mode with independent factory methods |
| Two beans use two different dependency objects despite expecting singleton | Lite config is calling `otherBean()` directly | Switch to method parameter injection |
| `getBean(Engine.class)` differs from object created via `new Config().engine()` | Configuration instance created outside Spring | Only obtain managed beans through container or injection |
| `@Configuration(proxyBeanMethods=false)` mistaken for disabling `@Bean` | Confusing interception with bean definition processing | Spring still registers `@Bean` methods; it just does not intercept direct calls |
| Full mode still shows multiple objects | Target scope is prototype or code constructs objects outside container | Check bean scope, lookups, and call sites before blaming CGLIB |
| Singleton bean's method runs multiple times due to manual calls | Using lite method as a plain Java factory | Do not call methods directly when expecting container-managed references |
| Switching to full mode to "fix" every DI issue | Broken dependency graph/missing bean/qualifier | Fix DI configuration; `proxyBeanMethods` does not conjure missing dependencies |
| Spring AOP `@Transactional` does not run on self-call | AOP proxy self-invocation differs from config CGLIB enhancement | Route calls across proper proxy/interface/service boundaries |
| Static `@Bean` method not intercepted by CGLIB | Static methods are not virtual methods | Use BeanFactory/injection to obtain the bean |
| Java JPMS throws reflection/enhancement error | Module/package not opened properly | Check `opens`/`exports` in module descriptor |
| Unit test `new AppConfig().car()` differs from integration test | Unit test invokes config as a plain Java object | Use `AnnotationConfigApplicationContext` to test Spring semantics |
| Circular bean dependency appears | Bean A needs B while B needs A | Refactor dependency graph; do not just flip proxy mode |
| Manually added CGLIB yet still fails | Class/method constraint or config semantics, not a missing JAR | Use Spring's repackaged CGLIB; inspect the actual error and code |
| Slow startup | Various causes (scanning, bean creation, network, post-processors) | Profile specifically; do not assume `proxyBeanMethods=false` fixes everything |

### 10.1. Verifying the right configuration object

If you need to verify full enhancement, create a real context and inspect behavior:

```java
try (var context =
        new AnnotationConfigApplicationContext(FullConfig.class)) {
    Engine engine = context.getBean(Engine.class);
    Vehicle car = context.getBean("car", Vehicle.class);
    System.out.println(engine == car.engine());
}
```

This is an **illustrative excerpt** using `FullConfig`, `Engine`, and `Vehicle` from section 7. It must be run in code with access to those classes; `AnnotationConfigApplicationContext` is the exact class from `org.springframework.context.annotation`.

Do not decide whether enhancement is active solely from the runtime class name; **bean identity and scope** reflect the behavior you actually need.

### 10.2. Debug checklist when extra objects are created

1. Confirm `@Configuration` was processed by Spring in the actual context.
2. Check whether `proxyBeanMethods` defaults to `true` or was disabled.
3. Find places calling `otherBean()` directly; replace with method parameters where possible.
4. Check whether the target scope is singleton, prototype, or custom.
5. Check whether the object was created via `new` outside the BeanFactory.
6. Check for duplicate bean names or multiple beans of the same type causing wrong candidate selection.
7. If AOP is present, distinguish proxy references from raw targets.
8. Test on a minimal context to reproduce identity as in section 7.
9. Do not rely on a lone constructor log to infer lifetime when `FactoryBean`/proxies are involved.
10. When choosing lite mode, ensure no inter-bean direct calls remain that require container semantics.

## 11. Knowledge Check Exercises

### Exercise 1 — Predicting Engine count

In `FullConfig` from section 7, `engine` is a singleton and two factory methods call `engine()` directly. How many `Engine`s are created?

**Answer:** one managed `Engine` in the example's context; both inter-bean references are intercepted and routed back to the BeanFactory.

### Exercise 2 — Disabling interception

Change `FullConfig` to `@Configuration(proxyBeanMethods=false)` without changing the method bodies. What are the three identity comparison results?

**Answer:** in the example, all `false`. There is one managed `Engine` singleton plus two `Engine` instances created by direct calls inside `car()` and `truck()`.

### Exercise 3 — Sharing a singleton without proxying

Wanting to keep `proxyBeanMethods=false`, how do `car`/`truck` receive the same managed `engine`?

**Answer:** use `@Bean Vehicle car(Engine engine)` and `@Bean Vehicle truck(Engine engine)` and pass the parameter into the constructor; Spring resolves the argument from the BeanFactory.

### Exercise 4 — `final class`

Why is `@Configuration final class AppConfig` invalid in full mode?

**Answer:** CGLIB must generate a subclass to override `@Bean` methods. `final` prevents inheritance.

### Exercise 5 — Singleton and prototype

`@Bean @Scope("prototype") Engine engine()` in full config. Does every normal lookup return a single shared `Engine` like a singleton?

**Answer:** no; the container honors the scope. CGLIB inter-bean lookup does not turn a prototype into a singleton.

### Exercise 6 — Direct method call from Java `new`

Does `new FullConfig().engine()` automatically go through the BeanFactory?

**Answer:** no. That is an instance created outside the container, not the managed CGLIB-enhanced configuration bean.

### Exercise 7 — Comparing with `@Transactional` self-invocation

Does the fact that `car()` calling `engine()` is intercepted in full config prove that `@Transactional` on a service method will always trigger when that service calls another method on itself via `this`?

**Answer:** no. The two mechanisms differ; self-invocation on the target normally bypasses the Spring AOP proxy.

### Exercise 8 — Library scenario

An application has three independent factory methods that do not call each other and only accept Spring-resolved parameters. Is enabling `proxyBeanMethods=true` necessary?

**Answer:** no. `@Configuration(proxyBeanMethods=false)` is a sensible choice when inter-bean calls are not needed; `@Bean` methods still create managed beans.

### Exercise 9 — A bean needing a fresh prototype on every use

If a singleton `JobRunner` needs a prototype `JobTask` on every run, is passing `JobTask` as a parameter `@Bean JobRunner runner(JobTask task)` enough?

**Answer:** no; direct injection into a singleton resolves only one task when the runner is created. Use `ObjectProvider<JobTask>` or an appropriate factory and look it up each time it is needed.

### Exercise 10 — Checking errors at the right layer

A `@Bean` method fails to resolve its `Repository` parameter. Will switching `proxyBeanMethods=true` to `false` definitely fix it?

**Answer:** no. That is a missing dependency or candidate resolution error; register the repository, fix qualifiers/scanning/conditions, rather than merely changing method interception mode.

## 12. Design Checklist

Before choosing full or lite configuration:

- Do `@Bean` methods **genuinely call one another directly** and need lookup with BeanFactory semantics?
- If so, can they be replaced with **method parameter injection** to reduce coupling?
- Does the bean use singleton or another scope? Are `@Lazy`, prototype, scoped proxies, or AOP affecting identity?
- Are `final` classes, records, or non-overridable members needed? If so, avoid full-mode interception and verify the configuration appropriately.
- Are `@Bean` methods being called on `new Config()` outside Spring?
- Are **managed singleton instances** clearly distinguished from raw objects created by direct Java calls?
- With Spring AOP, has self-invocation been checked against AOP proxy rules independently without using CGLIB config behavior as a proxy analogy?
- Has a context test confirmed actual identity, lifecycle, and bean registration?

## 13. Summary

**Full `@Configuration`** has `proxyBeanMethods=true` by default. Spring enhances the configuration class with a **CGLIB subclass** so eligible calls between `@Bean` methods are routed to the BeanFactory, preserving singleton/scope/AOP semantics of managed beans. It requires classes/methods to be subclassable/overridable; it does not apply the same interception to static factory methods.

**Lite mode** with `@Configuration(proxyBeanMethods=false)` still registers and manages `@Bean`s, yet Java calls like `otherBean()` are not intercepted and can construct objects outside the managed bean the caller expected. The clean style compatible with both modes is **factory-method parameter injection**: `@Bean Car car(Engine engine)`.

When inter-bean direct calls are needed in full configuration, use that mechanism deliberately. When factory methods are independent or already declare parameter dependencies, lite mode is usually simpler and easier to maintain. Whichever mode you choose, verify behavior with a real Spring context instead of calling Java methods on a manually instantiated `new` configuration.

### Official Documentation

- [Spring Framework 6.2 — Using the `@Configuration` Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/configuration-annotation.html).
- [Spring Framework 6.2 — Using the `@Bean` Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html).
- [Spring Framework 6.2 — Basic Concepts: `@Bean` and `@Configuration`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/basic-concepts.html).
- [Spring Framework 6.2 — `Configuration` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/Configuration.html).
- [Spring Framework 6.2 — `Bean` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/Bean.html).
