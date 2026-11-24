# Lookup Method Injection with @Lookup in Spring Framework

## 1. The Problem: A Singleton Needs a Shorter-Lived Bean

A Spring bean usually has `singleton` scope: within the same container, Spring supplies the same instance for lookups of that bean. Conversely, `prototype` scope creates a new instance every time the container receives a request to create/fetch the bean.

The issue arises when a singleton needs **a fresh prototype for each business execution**. The following direct injection approach does not meet that requirement:

```java
@Component
class BatchProcessor {
    private final WorkUnit workUnit;

    BatchProcessor(WorkUnit workUnit) {
        this.workUnit = workUnit;
    }

    void process() {
        workUnit.run();
    }
}
```

Suppose `WorkUnit` is registered under `prototype` scope. Spring resolves constructor dependencies **once when creating the `BatchProcessor` singleton**, so every call to `process()` reuses the exact same `workUnit` instance that was injected.

`@Lookup` solves the case where you need to **look up another bean at method invocation time**. The container generates a subclass at runtime to replace the body of a `@Lookup`-annotated method with a call to `BeanFactory`. As a result, the singleton can invoke the lookup method repeatedly and receive a fresh prototype each time.

> `@Lookup` does not by itself turn the target bean into a prototype. The scope of the **looked-up** bean still determines instance count: looking up a singleton repeatedly still returns the same singleton; looking up a prototype repeatedly yields new instances.

## 2. What Is @Lookup, and Where Is It Placed?

Full annotation: `org.springframework.beans.factory.annotation.Lookup`, with `@Target(METHOD)` and `@Retention(RUNTIME)`.

Two ways to specify the bean to look up:

```java
// Spring infers the target bean from the return type WorkUnit.
@Lookup
protected WorkUnit createWorkUnit() {
    throw new UnsupportedOperationException("Spring must override this method");
}

// Spring uses a specific bean name.
@Lookup("specialWorkUnit")
protected WorkUnit createSpecialWorkUnit() {
    throw new UnsupportedOperationException("Spring must override this method");
}
```

These are **two independent illustrative options**; a real class would use whichever option fits.

- `@Lookup`, without `value`: resolves the bean based on the method's **return type**, conceptually equivalent to `getBean(WorkUnit.class, ...)`.
- `@Lookup("specialWorkUnit")`: resolves by **bean name**, conceptually equivalent to `getBean("specialWorkUnit", ...)`. This is helpful when multiple beans share the same type.
- The method can be `abstract` or have a default body (stub). Spring overrides overridable methods when it instantiates the bean containing that method.
- The annotated method must be an **overridable instance method**; do not use `private`, `static`, or `final`.
- The class containing the lookup method must be subclassable; `final` classes are unsuitable.
- The return type should be the target bean type or a compatible supertype/interface; the target bean must exist and be resolvable in an active scope at lookup time.

If you declare a method body that throws an exception as above, the exception **will not occur** when calling a bean successfully created and enhanced by Spring, because the subclass invokes `BeanFactory` instead of the stub. The exception helps catch cases where someone instantiates the class directly with `new` or runs tests without Spring.

## 3. What Does Spring Do at Runtime?

Ideal execution flow:

```text
ApplicationContext creates BatchProcessor singleton
  -> detects @Lookup metadata on createWorkUnit()
  -> Spring generates dynamic subclass via CGLIB
  -> actual singleton is an instance of the subclass
  -> BatchProcessor.process()
      -> calls createWorkUnit() via virtual dispatch
      -> Spring-generated implementation invokes BeanFactory
      -> BeanFactory fetches/creates WorkUnit bean per configured scope
      -> returns WorkUnit to process()
```

This differs from `@Autowired` on fields/constructors, which resolves dependencies when the bean receives injection. `@Lookup` is a **dependency obtained when the method executes**.

One easy point of confusion: when the singleton's `process()` method calls `this.createWorkUnit()`, the call still enters the **overridden implementation in the subclass**, so a new lookup happens. In this situation, do not mechanically apply the Spring AOP proxy self-invocation rule; the `@Lookup` mechanism relies on method overriding on the container-created object itself.

However, that behavior holds only when:

1. The calling object is a **bean directly instantiated by the Spring container**, with method injection applied.
2. The lookup method is overridable.
3. The target bean is registered and its scope is active.
4. Lookup is not invoked on an instance created manually via `new`.

## 4. Complete Java 17+ Example: Singleton Obtaining Fresh Prototypes

The example uses Spring Framework 6.2.x and Java 17, without Spring Boot. Create the structure:

```text
lookup-demo/
  settings.gradle
  build.gradle
  src/main/java/LookupDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'lookup-demo'
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

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'LookupDemo'
}
```

`src/main/java/LookupDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.annotation.Lookup;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Scope;
import org.springframework.stereotype.Component;

public class LookupDemo {

    @Component
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    public static class WorkUnit {
        private static final AtomicInteger NEXT = new AtomicInteger();
        private final int id = NEXT.incrementAndGet();

        public int id() {
            return id;
        }
    }

    @Component("namedTask")
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    public static class NamedTask {
        private final String label;

        public NamedTask(String label) {
            this.label = label;
        }

        public String label() {
            return label;
        }
    }

    @Component
    public static class WorkManager {
        private final WorkUnit constructorInjected;

        // Injected only once when creating singleton WorkManager.
        public WorkManager(WorkUnit constructorInjected) {
            this.constructorInjected = constructorInjected;
        }

        public WorkUnit fixedUnit() {
            return constructorInjected;
        }

        // Spring looks up the bean by return type WorkUnit.
        @Lookup
        protected WorkUnit createUnit() {
            throw new UnsupportedOperationException(
                    "Only Spring-managed instances support this lookup");
        }

        // Spring looks up the bean by name and passes label to the constructor.
        @Lookup("namedTask")
        protected NamedTask createNamedTask(String label) {
            throw new UnsupportedOperationException(
                    "Only Spring-managed instances support this lookup");
        }

        public WorkUnit newUnit() {
            return createUnit();
        }

        public NamedTask newNamedTask(String label) {
            return createNamedTask(label);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            // Spring must instantiate the registered bean definitions itself.
            context.register(WorkUnit.class, NamedTask.class, WorkManager.class);
            context.refresh();

            WorkManager manager = context.getBean(WorkManager.class);

            WorkUnit fixed1 = manager.fixedUnit();
            WorkUnit fixed2 = manager.fixedUnit();
            WorkUnit fresh1 = manager.newUnit();
            WorkUnit fresh2 = manager.newUnit();

            NamedTask task1 = manager.newNamedTask("alpha");
            NamedTask task2 = manager.newNamedTask("beta");

            System.out.println("sameSingleton="
                    + (manager == context.getBean(WorkManager.class)));
            System.out.println("fixedSame=" + (fixed1 == fixed2));
            System.out.println("lookupFresh=" + (fresh1 != fresh2));
            System.out.println("lookupDiffFromFixed="
                    + (fresh1 != fixed1 && fresh2 != fixed1));
            System.out.println("taskNames="
                    + task1.label() + "," + task2.label());
            System.out.println("namedTaskFresh=" + (task1 != task2));
        }
    }
}
```

Run with Gradle 8+ installed:

```bash
gradle run --quiet
# If Gradle Wrapper is already present:
# ./gradlew run --quiet
```

Lines printed by the program's `System.out.println` statements:

```text
sameSingleton=true
fixedSame=true
lookupFresh=true
lookupDiffFromFixed=true
taskNames=alpha,beta
namedTaskFresh=true
```

Do not rely on specific `id` values to interpret output, because bean initialization order can change when extending the example. What matters is **object identity**.

**Explanation of results:**

1. `WorkManager` is a singleton; looking up the same bean still returns the same manager.
2. `fixed1 == fixed2` because that dependency was injected once when creating the manager.
3. `createUnit()` is overridden by Spring, calling `BeanFactory` for type `WorkUnit` each time; `WorkUnit` has prototype scope, so each call produces a new instance.
4. `@Lookup("namedTask")` specifies the exact bean name; the two string parameters are passed as **constructor arguments** when the prototype `NamedTask` bean is created, yielding labels `alpha` and `beta` respectively.
5. The two `NamedTask` instances also differ in identity because the bean has prototype scope.

Spring may emit logs outside the `System.out` lines; those are not stdout printed by the example logic itself.

## 5. Passing Arguments to a Lookup Method

According to the `@Lookup` Javadoc, when a lookup method has parameters, Spring forwards them as arguments to the `BeanFactory.getBean(...)` call to serve as **constructor or factory method arguments** of the target bean.

Concise example:

```java
@Lookup("namedTask")
protected NamedTask createNamedTask(String label) {
    return null; // Body overridden by Spring at runtime.
}

// When called from a Spring-enhanced bean:
NamedTask task = createNamedTask("invoice-42");
```

This is an illustrative excerpt, not a standalone program. A bean named `namedTask` must exist with a constructor/factory method capable of accepting the corresponding `String`. Lookup methods do not "auto-bind" arbitrary arguments like business methods: each parameter must match how Spring constructs the bean.

Distinguish clearly:

- `@Lookup` does not replace `@Value`, `@Autowired`, or fixed dependency configuration.
- Runtime arguments passed through lookup are mainly suited for newly created beans (typically `prototype`).
- Never assume you can alter constructor arguments of an existing singleton: singleton scope retains the existing instance.
- If the target bean has overloaded constructors/factory methods, design unambiguous signatures or register the bean in a less ambiguous way.

## 6. Lookup by Name or by Return Type?

### By Type: @Lookup

```java
@Lookup
protected WorkUnit createUnit() {
    return null;
}
```

The advantage is avoiding string-based bean names, suitable when only one candidate resolves for type `WorkUnit`. If multiple beans share the type, configure `@Primary`/`@Qualifier` on the definition or choose lookup by name per business needs. Do not assume an unnamed lookup will arbitrarily pick a bean when resolution is ambiguous.

### By Name: @Lookup("beanName")

```java
@Lookup("specialWorkUnit")
protected WorkUnit createSpecialUnit() {
    return null;
}
```

This requests the exact bean `specialWorkUnit`, provided the bean exists and its type is compatible with the return type. A wrong bean name causes lookup to fail at runtime when the method is called. If a bean name changes during refactoring, the corresponding string must be updated.

Neither form **adds caching at the lookup method**; only the target bean's scope decides whether instances are reused.

## 7. Important Limitations of @Lookup

### 7.1. Both Class and Method Must Allow Overriding

Spring generates a runtime subclass. The following declarations cannot be used for overriding:

```java
// Cannot be used as a bean needing subclassing to implement @Lookup.
public final class FinalManager {
    // ...
}

// final method cannot be overridden.
@Lookup
public final WorkUnit createUnit() {
    return null;
}

// private method is not a virtual override point.
@Lookup
private WorkUnit createPrivateUnit() {
    return null;
}
```

These are **illustrative anti-examples**; do not combine them into the runnable example in section 4. `static` methods likewise cannot be overridden by this instance-subclassing mechanism. In Kotlin projects, classes/methods are final by default, so you must ensure openness (e.g., via `open` or an appropriate compiler plugin).

### 7.2. @Lookup Does Not Work on Beans Returned from @Bean Factory Methods

Spring needs **control to instantiate the class via the container's subclassing mechanism**. The following is not a reliable way to activate `@Lookup`:

```java
@Configuration
class AppConfig {
    @Bean
    WorkManager workManager(WorkUnit workUnit) {
        return new WorkManager(workUnit);
    }
}
```

This is an illustrative anti-example on the same `WorkManager` type from section 4. Although Spring manages the bean after the factory method returns, the instance was constructed via `new WorkManager(...)` inside the `@Bean` method. The container cannot replace the already-returned object with a dynamically generated subclass for the lookup method. Calling `newUnit()` on that instance can cause the `createUnit()` stub to throw `UnsupportedOperationException`.

**The right way** is to let Spring instantiate the class containing `@Lookup` directly, for example:

```java
context.register(WorkManager.class);
```

or annotate with `@Component` and enable appropriate component scanning so Spring processes the bean definition from the class; ensure you do not simultaneously register another `WorkManager` bean via `@Bean` and create ambiguity.

If you genuinely need a `@Bean` factory method to construct the manager (for example due to special constructor logic), use `ObjectProvider<WorkUnit>` as in section 9 instead of `@Lookup`.

### 7.3. Manually Calling `new` Does Not Activate the Container

```java
WorkManager manager = new WorkManager(new WorkUnit());
manager.newUnit(); // Stub throws, because there is no Spring-generated subclass.
```

`@Lookup` is not a Java reflection mechanism that turns every instance of a class into a Spring bean. Only container-created objects with lookup overrides exhibit the expected behavior.

### 7.4. @Lookup Does Not Create Scopes or Propagate Contexts

- Target bean scope singleton -> repeated lookups still return the single singleton.
- Target bean scope prototype -> each lookup normally returns a new instance.
- Target bean scope request/session -> an active request/session scope must exist. Calling outside a suitable context can fail with an inactive-scope error.
- A lookup executing on an `@Async` worker resolves the bean using **whatever context exists on the thread calling the lookup**, without automatically copying HTTP request or thread-local context from the originating thread.

### 7.5. Prototype Lifecycle Remains the Caller's Responsibility

`@Lookup` only requests **fetching a bean**, adding no destruction semantics. For prototype scope, Spring runs normal initialization steps but does not automatically call destruction callbacks for each prototype after the caller finishes using it.

Therefore, `@PreDestroy` or `DisposableBean.destroy()` on a prototype will typically **not run automatically** simply because of method lookup or when closing the context. If the bean needs to close resources, design explicit cleanup in the caller. For instance, with a prototype implementing `AutoCloseable`:

```java
try (ExpensiveUnit unit = manager.newExpensiveUnit()) {
    unit.execute();
}
```

This is an **illustrative design snippet**: it assumes `ExpensiveUnit implements AutoCloseable` and the manager has a matching lookup method. You must ensure `close()` has proper semantics and the bean is not reused after closing.

## 8. Distinguishing Lookup Methods from @Bean, Scoped Proxies, and ObjectProvider

| Mechanism | When dependency is chosen | Requirements | When to use |
| --- | --- | --- | --- |
| Direct prototype injection into singleton constructor | Once when creating the singleton | Prototype bean definition exists | Singleton holds one fixed collaborator; **unsuitable** if a fresh instance is needed each time |
| `@Lookup` | Every time the lookup method is called | Bean containing method must be instantiated by Spring via class and method must be overridable | Want to hide `BeanFactory` from business code while needing a fresh prototype per use |
| `ObjectProvider<T>.getObject()` | Every time caller invokes the provider | Provider injection works even with beans returned from `@Bean` factory methods | Want explicit dependency lookup, easy testing, and less reliance on subclassing |
| Scoped proxy | Every time a method is called on the proxy (resolves target per scope) | Scope configured with proxy and currently active | Long-lived bean holds a proxy to a shorter-lived target, e.g., request scope |
| `ApplicationContext.getBean(...)` | Every time container is called | Caller must hold context/`BeanFactory` | Tooling, infrastructure; business code accepts direct coupling to Spring container |

A subtle difference: a **scoped proxy** typically maintains a proxy reference inside the singleton, whereas `@Lookup` makes the method return **the target bean looked up at that exact call**. With a prototype, you can obtain an instance and call multiple methods on it in sequence before fetching the next instance; with a prototype proxy, each method invocation on the proxy may resolve a new target (depending on proxy/scope behavior). Choose according to how the collaborator is actually used.

## 9. Alternative Solution Using ObjectProvider

`ObjectProvider<T>` often expresses intent more clearly than `@Lookup`, especially when the class is created by a `@Bean` factory method or needs unit testing without Spring.

Complete class logic illustration:

```java
import org.springframework.beans.factory.ObjectProvider;

public final class WorkManagerWithProvider {
    private final ObjectProvider<WorkUnit> units;

    public WorkManagerWithProvider(ObjectProvider<WorkUnit> units) {
        this.units = units;
    }

    public int runOnce() {
        WorkUnit unit = units.getObject();
        return unit.id();
    }
}
```

This snippet is **an illustrative class**, assuming `WorkUnit` is defined as in section 4 and the provider is injected by Spring. There is no requirement to subclass `WorkManagerWithProvider`; the class can be `final`.

Declaration in a configuration class:

```java
@Configuration(proxyBeanMethods = false)
class ProviderConfig {
    @Bean
    WorkManagerWithProvider providerManager(
            ObjectProvider<LookupDemo.WorkUnit> units) {
        return new WorkManagerWithProvider(units);
    }
}
```

Here you need `ObjectProvider<LookupDemo.WorkUnit>` and corresponding imports for `ObjectProvider`, `Bean`, and `Configuration`. This is an **illustrative configuration snippet**, not code to add to `LookupDemo.java` for section 4's program to run. With a prototype `WorkUnit`, each `getObject()` resolves a new prototype.

If runtime constructor args must be passed, `ObjectProvider.getObject(Object... args)` provides an appropriate overload (ensure the target bean supports constructor/factory arguments). For ordinary beans needing no arguments, `getObject()` is simplest.

**Why is a provider easier to test?** In unit tests, you can supply a fake provider returning desired `WorkUnit` instances and verify call counts and results—without booting a Spring `ApplicationContext` or relying on CGLIB.

## 10. Testing @Lookup Properly

### Integration Test via Spring Container

Key assertions:

```java
WorkManager manager = context.getBean(WorkManager.class);
WorkUnit a = manager.newUnit();
WorkUnit b = manager.newUnit();

assert a != b;                      // When WorkUnit is prototype.
assert manager.fixedUnit()
        == manager.fixedUnit();      // Fixed constructor injection.
assert a != manager.fixedUnit();
```

This is an excerpt from section 4's sample; it assumes `context` is properly initialized and the JVM runs with `-ea` if using Java `assert`. In real projects, prefer JUnit 5 `assertNotSame` and container-backed testing.

### Pure Unit Test Without Booting Spring

For a **concrete** (non-abstract) lookup method, you can create a test subclass overriding the method:

```java
class TestWorkManager extends LookupDemo.WorkManager {
    TestWorkManager(LookupDemo.WorkUnit unit) {
        super(unit);
    }

    @Override
    protected LookupDemo.WorkUnit createUnit() {
        return new LookupDemo.WorkUnit();
    }
}
```

This is a test helper class, not part of the main example. Spring can subclass at runtime, whereas in unit tests you provide the implementation explicitly. If the lookup method is declared `abstract`, unit tests must likewise implement the method before instantiating the class.

If a test merely calls `new WorkManager(...)` and expects `@Lookup` to work automatically, that test bypasses the mechanism Spring provides. An integration test with `AnnotationConfigApplicationContext` is the accurate way to verify wiring and enhancement.

### Scenarios to Include in Tests

1. Two lookups of the same prototype return **different references**.
2. Two lookups of the same singleton return **the same reference**.
3. When no name is specified and multiple beans share the type, resolution configuration must unambiguously select one candidate.
4. `@Lookup("x")` must point to an actually registered bean name.
5. Methods with runtime args must forward parameters properly to the constructor/factory method.
6. Owner beans created by a factory method must not be expected to have lookup overrides.
7. Scoped beans such as request/session must be called inside a valid context.
8. If prototypes hold resources, tests must verify cleanup in the caller.

## 11. Common Errors and How to Diagnose Them

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Every call still returns the same object | Target bean is actually `singleton` | Inspect `@Scope("prototype")`/bean definition, not just the method annotation |
| Lookup method stub gets executed | Owner instantiated via `new` or `@Bean` factory method returning a constructed instance | Let Spring instantiate the owner from its class definition, or switch to `ObjectProvider` |
| Cannot generate subclass/override | `final` class, `final`/`private`/`static` method | Use an overridable class and instance method |
| `NoUniqueBeanDefinitionException` | Type-based lookup has multiple ambiguous candidates | Specify `@Lookup("beanName")` or disambiguate bean selection |
| `NoSuchBeanDefinitionException` | Target bean not registered, wrong name, wrong type | Check bean name, component scan, config conditions, return type |
| Scope not active | Looking up request/session bean outside a valid context | Move lookup inside an active scope, or redesign data boundaries |
| Runtime args do not match constructor | Method parameters mismatch bean creation signature | Design constructor/factory method to accept matching arguments |
| Prototypes hold resources forever | Mistakenly assuming `@Lookup` triggers destruction callbacks | Caller closes resources explicitly; use `try-with-resources`/`finally` |
| Unit test throws `UnsupportedOperationException` | Test uses plain Java object without Spring enhancement | Subclass stub, inject a provider, or run an integration test |
| Failure in native-image/AOT or environment restricting dynamic subclasses | Design relies on runtime-generated subclasses | Verify target build/runtime tooling; consider `ObjectProvider` to reduce reliance on dynamic method replacement |

Note: specific exceptions may be wrapped by Spring in higher-level exceptions when errors occur during bean creation. Always inspect the **root cause** (not just the outermost exception).

## 12. When Should You Choose @Lookup?

Choose `@Lookup` when all of the following hold:

- There is a container-created bean that must live long-term (typically a singleton).
- It must obtain another bean at **the exact moment of use**.
- The target bean's scope is well defined, usually prototype.
- The class containing the method is instantiated directly by Spring, is subclassable, and the method is overridable.
- You accept container-generated subclassing and want a concise lookup API.

Prefer `ObjectProvider` or a factory abstraction when the class might be created via `@Bean`, easy mocking/unit testing is required, or you want a structure less coupled to bytecode method injection. Use a scoped proxy when you want to inject one reference where every call resolves the target according to the active scope.

Do not rely on `@Lookup` by default to solve **thread safety** or resource lifetime management: each prototype is merely a fresh object, while concurrent access and resource closing still require deliberate design.

## 13. Official Sources

- [Spring Framework Reference — Method Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-method-injection.html): lookup mechanics, CGLIB, abstract/concrete methods, and factory method limitations.
- [Spring Framework API — @Lookup (6.2.x)](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/annotation/Lookup.html): annotation declaration, selecting targets by type/name, passing runtime arguments to `BeanFactory`.
- [Spring Framework Reference — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): singleton/prototype lifecycle and why constructor-injecting a prototype into a singleton does not create a new instance per invocation.
- [Maven Central — spring-context 6.2.18](https://central.sonatype.com/artifact/org.springframework/spring-context/6.2.18): artifact version for the Gradle example.

Core principles: `@Lookup` is **dependency lookup via a Spring-overridden method**, not a scope-changing annotation; the target's scope, how the owner is created, and the target's lifecycle must all be established independently.
