# Direct Inter-Bean Method Call Behavior Between @Bean Methods in Spring Core Container

## 1. Goal and Scenario

In Spring Java configuration, we may see one `@Bean` method directly calling another `@Bean` method:

```java
@Configuration
public class ShopConfig {

    @Bean
    StockRepository stockRepository() {
        return new StockRepository();
    }

    @Bean
    StockService stockService() {
        return new StockService(stockRepository());
    }
}
```

`StockRepository` and `StockService` in the opening snippet are two illustrative business classes that must be defined and imported to compile. Looking like plain Java, `stockRepository()` would run every time it is called, potentially creating extra objects. Yet with **full `@Configuration`**, Spring alters this call's behavior via **CGLIB method interception**, so references through `@Bean` methods still pass through the container and obey scope. When **interception is disabled** or **lite `@Bean`** is used, that exact same Java syntax can actually construct new objects rather than Spring-managed objects.

This is one of the most important distinctions when learning Java configuration.

After this lesson, you will be able to:

1. Explain how full `@Configuration` and lite `@Bean` differ when one factory method calls another factory method.
2. Predict object identity, instantiation count, and `singleton` vs. `prototype` behavior in each mode.
3. Understand the conditions for interception, along with constraints involving `final`, `private`, `static`, and CGLIB.
4. Distinguish **the container calling a method to create a bean** from **user code calling a method in Java**.
5. Use **`@Bean` method parameters** instead of cross-method calls to express dependencies consistently with `@Configuration(proxyBeanMethods=false)`.
6. Spot subtle bugs such as two DataSources, two mappers, two connection pools, or lifecycle callbacks not running on extra objects.
7. Run a Spring Framework 6.2.x, Java 17+ example comparing full configuration, lite configuration, and parameter injection, with deterministic stdout.

**Scope:** Spring Core Container's mechanism for **direct calls between `@Bean` methods**. Do not confuse this with a bean's business method calling another method, Spring AOP self-invocation, or regular field dependency injection.

## 2. @Bean Is a Factory Method, Yet Spring Can Intercept the Call

The `@Bean` annotation tells Spring to register a bean definition produced by the corresponding method:

```java
@Bean
Clock clock() {
    return Clock.systemUTC();
}
```

This snippet requires importing `org.springframework.context.annotation.Bean` and `java.time.Clock`, placed inside a configuration class loaded by Spring. The container knows there is a bean named `clock` (unless configured otherwise), with return type `Clock`, and can invoke the factory method when an instance is needed.

Two different operations:

- **Container-managed lookup:** `context.getBean("clock", Clock.class)` requests a bean managed by Spring. Regular singletons are returned from cache after initial creation.
- **Direct Java call:** `clock()` or `config.clock()` looks like a normal Java method call. Whether it is routed through the container depends on the **configuration class's processing mode** and whether the method is overridden/intercepted.

Thus, never give a simplistic answer like "calling any `@Bean` method always creates a new object" or "calling a `@Bean` method always returns a singleton". Both can be wrong.

## 3. Categorizing Direct Calls Between Factory Methods

### 3.1. Full `@Configuration`

With default `@Configuration` (`proxyBeanMethods=true`), Spring enhances the configuration instance with CGLIB. An **eligible `otherBean()` call on the enhanced config** can be routed back to `BeanFactory`: singletons are shared and other scopes are applied per container rules.

### 3.2. Lite `@Configuration(proxyBeanMethods=false)`

Bean definitions are still registered and managed, yet a directly called `otherBean()` method executes its body like plain Java. If the body constructs a new object, that object can live outside the managed singleton. Do not mistake this object for a prototype bean.

### 3.3. `@Bean` inside a plain `@Component`

Spring can discover factory methods in a scanned/registered `@Component` class, yet they carry **lite** semantics for inter-bean calls. `@Component` does not equal full `@Configuration`.

### 3.4. Call routing table

| Call | BeanFactory semantics? |
| --- | --- |
| `context.getBean("repository")` | Yes, regardless of full/lite |
| `repository()` on enhanced full config | Yes if the instance method is validly intercepted |
| `repository()` on lite config / plain `@Component` | No, executes body directly |
| `staticRepository()` on any config | Does not intercept static calls |
| `new FullConfig().repository()` outside Spring | No enhancement |

Merely seeing `@Bean` on a method is not enough to conclude a method call will return a container bean; you must examine **the receiver and the call path**.

## 4. Why Does Full Configuration Use CGLIB?

Spring must distinguish a **factory invocation to build a bean** from a **bean-reference call** when one `@Bean` method calls another `@Bean` method. With full config, CGLIB creates a subclass and overrides eligible methods to route reference calls to the BeanFactory:

```text
BeanFactory creates serviceA
    -> enhancedConfig.serviceA()
    -> repository() is intercepted
    -> BeanFactory fetches 'repository' bean per scope
    -> serviceA receives managed reference
```

If the bean is a singleton, consumers share the same bean; if it is a prototype or custom scope, the container enforces that exact scope. If the bean is wrapped in an AOP/scoped proxy, the reference returned by the container may be the proxy rather than the raw object created by `new` inside the factory body. That difference is observable through identity and lifecycle.

### 4.1. A factory call is not always a lookup

When BeanFactory is actively creating the corresponding bean, the interceptor must let the factory body execute; when the enhanced configuration calls a method to **reference another bean**, the interceptor performs a lookup. Without distinguishing those two cases, it is easy to misunderstand it as an infinite recursion or a plain Java cache for all calls. This is a conceptual model, not internal CGLIB source code.

### 4.2. Full configuration limitations

Subclassing/overriding requires the configuration class not to be `final` and instance `@Bean` methods not to be `private`/`final`; `static @Bean` is not overridden. Creating `new Config()` outside Spring has no enhancement. When lite configuration is desired, **passing dependencies via `@Bean` parameters** is the more stable pattern.

## 5. The Safe Approach: Injecting Dependencies via @Bean Parameters

Replace:

```java
@Configuration(proxyBeanMethods = false)
class Config {
    @Bean
    Repository repository() {
        return new Repository();
    }

    @Bean
    Service service() {
        return new Service(repository()); // Java direct call!
    }
}
```

with:

```java
@Configuration(proxyBeanMethods = false)
class Config {
    @Bean
    Repository repository() {
        return new Repository();
    }

    @Bean
    Service service(Repository repository) {
        return new Service(repository); // Spring resolves the dependency.
    }
}
```

`Repository` and `Service` are illustrative types. In the second variant, Spring resolves the `Repository` parameter from bean definitions, applying scope/qualifier/primary like any other injection point. Neither enhancement nor cross-method calls are needed to share beans.

**Benefits:**

- Works with the exact same principle in full mode and lite mode.
- Dependency graph is visible in the method signature.
- Easy to disambiguate multiple implementations with `@Qualifier`.
- Easy to catch missing or ambiguous dependency errors.
- Avoids accidentally creating extra clients/connection pools/mappers outside the container.
- Reduces reliance on CGLIB and how Spring handles method calls.
- Enables `@Configuration(proxyBeanMethods=false)` without altering expected dependency semantics.

In modern Java configuration, this is usually the most readable and least surprising choice.

## 6. Complete Java 17+ Example: Comparing Three Modes

This practical example uses no Spring Boot, JDBC, or web server. It uses **Spring Framework 6.2.9**, **JDK 17+**, and `AnnotationConfigApplicationContext`.

We test three **separate** contexts:

1. **FullConfig:** default `@Configuration` intercepts cross-calls to `widget()`.
2. **LiteConfig:** `@Configuration(proxyBeanMethods=false)` lets `widget()` inside `pair()` run as plain Java.
3. **ParamConfig:** also disables interception, yet `pair(Widget widget)` receives its parameter from the container and therefore still uses the registered singleton.

`Widget` is a simple object with an id. Each time the factory body actually constructs an object, a counter increments. `Pair` holds two references to `Widget`. Comparison uses the `==` operator to test **object identity**, independent of `equals()`.

### 6.1. Project structure

```text
interbean-calls-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── demo/
                └── InterBeanCallsDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'interbean-calls-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.9'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.InterBeanCallsDemo'
}
```

**`src/main/java/demo/InterBeanCallsDemo.java`**

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class InterBeanCallsDemo {
    private static final AtomicInteger FULL_CALLS = new AtomicInteger();
    private static final AtomicInteger LITE_CALLS = new AtomicInteger();
    private static final AtomicInteger PARAM_CALLS = new AtomicInteger();

    // Java 17 record: immutable value holding the factory invocation identifier.
    record Widget(int id) {}
    record Pair(Widget first, Widget second) {}

    // Full mode: method interception enabled by default.
    @Configuration
    public static class FullConfig {
        @Bean
        public Widget widget() {
            return new Widget(FULL_CALLS.incrementAndGet());
        }

        @Bean
        public Pair pair() {
            return new Pair(widget(), widget());
        }
    }

    // Lite mode: cross calls are ordinary Java calls.
    @Configuration(proxyBeanMethods = false)
    public static class LiteConfig {
        @Bean
        public Widget widget() {
            return new Widget(LITE_CALLS.incrementAndGet());
        }

        @Bean
        public Pair pair() {
            return new Pair(widget(), widget());
        }
    }

    // No interception, yet uses method argument injection.
    @Configuration(proxyBeanMethods = false)
    public static class ParamConfig {
        @Bean
        public Widget widget() {
            return new Widget(PARAM_CALLS.incrementAndGet());
        }

        @Bean
        public Pair pair(Widget widget) {
            return new Pair(widget, widget);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(FullConfig.class)) {
            Widget managed = context.getBean(Widget.class);
            Pair pair = context.getBean(Pair.class);

            System.out.println("full.calls=" + FULL_CALLS.get());
            System.out.println("full.pairSame="
                    + (pair.first() == pair.second()));
            System.out.println("full.managedSame="
                    + (pair.first() == managed));
            System.out.println("full.externalCallManaged="
                    + (context.getBean(FullConfig.class).widget() == managed));
        }

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(LiteConfig.class)) {
            Widget managed = context.getBean(Widget.class);
            Pair pair = context.getBean(Pair.class);

            System.out.println("lite.calls=" + LITE_CALLS.get());
            System.out.println("lite.pairSame="
                    + (pair.first() == pair.second()));
            System.out.println("lite.managedSame="
                    + (pair.first() == managed));
            System.out.println("lite.externalCallManaged="
                    + (context.getBean(LiteConfig.class).widget() == managed));
            System.out.println("lite.callsAfterExternal=" + LITE_CALLS.get());
        }

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(ParamConfig.class)) {
            Widget managed = context.getBean(Widget.class);
            Pair pair = context.getBean(Pair.class);

            System.out.println("param.calls=" + PARAM_CALLS.get());
            System.out.println("param.pairSame="
                    + (pair.first() == pair.second()));
            System.out.println("param.managedSame="
                    + (pair.first() == managed));
        }
    }
}
```

Nested classes `FullConfig`, `LiteConfig`, and `ParamConfig` are declared `public static` so they can serve as Java configuration classes. Only `InterBeanCallsDemo` is a public top-level class; the file name matches the class name and requires no extra package structure.

`Widget`/`Pair` are nested records, suited to Java 17. Because the configuration classes are not `final` and the `@Bean` methods in full mode are `public`, Spring can enhance `FullConfig`.

### 6.2. Run

Inside the `interbean-calls-demo` root directory:

```bash
gradle run --quiet
```

If the project has the Gradle Wrapper, use `./gradlew run --quiet` (Linux/macOS) or `gradlew.bat run --quiet` (Windows). Running `javac InterBeanCallsDemo.java` standalone will not work without supplying Spring dependencies on the classpath; Gradle handles this.

**Stdout printed by the program itself:**

```text
full.calls=1
full.pairSame=true
full.managedSame=true
full.externalCallManaged=true
lite.calls=3
lite.pairSame=false
lite.managedSame=false
lite.externalCallManaged=false
lite.callsAfterExternal=4
param.calls=1
param.pairSame=true
param.managedSame=true
```

If Gradle or a logging framework emits extra logs, they are not part of the `System.out.println` output above.

### 6.3. Analyzing FullConfig

`widget` is a default singleton. BeanFactory creates one `Widget` instance via the factory body, incrementing `FULL_CALLS` to 1.

When `pair()` is invoked on the enhanced configuration, both `widget()` calls are intercepted to request the `widget` bean from the container. Since the singleton has already been created or is created on lookup, both references in `Pair` point to **the same bean**. Thus:

```text
full.calls=1
full.pairSame=true
full.managedSame=true
```

When external code fetches **the managed `FullConfig` bean itself** and calls `widget()`, the method is also enhanced. It returns the container-managed bean:

```text
full.externalCallManaged=true
```

**Important boundary:** if you write `new FullConfig()` yourself and call the method, that object did not go through Spring enhancement, so you must not expect the same behavior.

### 6.4. Analyzing LiteConfig

The container still has the `widget` and `pair` bean definitions, and creates regular singletons on refresh. Yet `pair()` calls `widget()` directly twice in its body, constructing two distinct objects. BeanFactory also creates a separate `Widget` for the `widget` bean definition, so total factory body invocations after refresh are **3**:

```text
lite.calls=3
lite.pairSame=false
lite.managedSame=false
```

Here `pair.first()` is not the managed widget singleton, even though the class and return type match. It was created by a **direct Java call** inside another factory method.

When fetching the managed `LiteConfig` bean and calling `widget()`, since there is no interception, that call creates an extra object, raising the counter to 4:

```text
lite.externalCallManaged=false
lite.callsAfterExternal=4
```

This does not mean Spring "does not manage `widget`" in lite mode. Spring **still manages the instance BeanFactory created for the `widget` bean**. The issue lies solely in **the extra objects created by direct method calls**.

### 6.5. Analyzing ParamConfig

`ParamConfig` is also in lite mode, yet `pair(Widget widget)` requests its dependency in the factory method signature. Spring resolves `Widget` from the context and supplies the managed singleton into the parameter. No method interception is needed:

```text
param.calls=1
param.pairSame=true
param.managedSame=true
```

This is the practical reason to prefer **method parameter injection** over directly calling another `@Bean` method whenever full mode is unnecessary.

### 6.6. Meaning of the counters

The counters only track how many times the `widget()` **factory method body** actually executes in each configuration. They do not count container lookups when a lookup returns a cached bean. `==` tests object reference equality. Because the source uses separate `AtomicInteger`s per configuration and creates/closes each context sequentially, the results are deterministic from the code without depending on BeanFactory map iteration order.

**Do not infer from the example that Spring always instantiates singletons in a fixed uncontracted order.** Whether `widget` or `pair` is instantiated first in the lite context, there are still three factory body invocations after refresh: one to build the managed `widget` and two direct calls from `pair()`.

## 7. Scope Directly Affects Inter-Bean Call Outcomes

Full mode preserves **scope**, rather than guaranteeing two `@Bean` calls always return the same object. Example:

```java
@Configuration
class ScopeConfig {
    @Bean
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    Widget widget() {
        return new Widget(1);
    }

    @Bean
    Pair pair() {
        return new Pair(widget(), widget());
    }
}
```

This structural example uses the `Widget`/`Pair` records from the full program; requires importing `Scope` and `ConfigurableBeanFactory`, or placing it in a scope with them. With `widget` as prototype, **each intercepted lookup from the two `widget()` calls requests a fresh prototype bean**. Thus `pair.first() != pair.second()` can be true, even in full mode.

Summary table:

| Cross-called bean | Full mode, called via enhanced config | Lite mode, direct call | Factory method parameter |
| --- | --- | --- | --- |
| `singleton` | Lookup to Spring-managed singleton, usually same instance | Runs method body, can create new out-of-container instance | Spring injects the same singleton by type/qualifier |
| `prototype` | Each lookup requests a prototype from BeanFactory | Runs method body, creates new instance **without full prototype bean lifecycle** | Spring resolves one prototype when constructing the parameterized bean |
| `request`/`session` | Lookup follows active scope | Direct method body can bypass scope semantics | Spring resolves dependency when creating the parameterized bean; may need scoped proxy/provider |
| `@Lazy` singleton bean | Lookup can trigger creation when needed | Runs body regardless of `@Lazy` on definition | Spring resolves per dependency; eager consumer can force lazy target early creation |

**Specifically for prototypes and singleton consumers:** if a singleton `Pair` accepts a prototype `Widget` parameter at creation time, it keeps **the one prototype instance resolved at that time**. To get a fresh prototype per business call, use `ObjectProvider<Widget>`, `Provider<Widget>`, or an appropriate lookup mechanism. Never call a `@Bean` method inside a business service to try to resolve scope.

### 7.1. Why is a direct call to a prototype also problematic?

Someone might argue: "A prototype is supposed to be new every time, so a lite direct call `widget()` still makes a new object—what's wrong with that?" The flaw is that **creating a new object does not mean receiving a Spring-managed prototype bean**.

An object created by a direct call can skip:

- Autowiring on the returned instance;
- `BeanPostProcessor`s and lifecycle initialization;
- Bean-specific proxying/AOP;
- Scope resolution or special dependencies;
- Other container rules tied to the bean definition.

Even if the instance count happens to match, **the semantics are not equivalent**.

## 8. Interception and the Lifecycle of Out-of-Container Objects

A familiar example is `DataSource`:

```java
@Bean
DataSource dataSource() {
    return buildPooledDataSource();
}

@Bean
JdbcTemplate jdbcTemplate() {
    return new JdbcTemplate(dataSource());
}
```

This is a structural example requiring the `spring-jdbc` dependency, `javax.sql.DataSource`, and an application-provided `buildPooledDataSource()` factory. With full config, `dataSource()` inside `jdbcTemplate()` can be intercepted to use the managed datasource singleton.

If the class is switched to `@Configuration(proxyBeanMethods=false)` while keeping the call, Spring can create:

1. One connection pool for the container-managed `dataSource` bean.
2. Another connection pool from the direct Java call inside `jdbcTemplate()`.

The second pool is not registered under the `dataSource` bean definition; resource management becomes hazardous: credentials, properties, connection metrics, and shutdown callbacks may diverge.

**Reliable approach:**

```java
@Bean
JdbcTemplate jdbcTemplate(DataSource dataSource) {
    return new JdbcTemplate(dataSource);
}
```

Now Spring resolves the managed datasource for the parameter. This snippet requires a validly registered `DataSource` bean; if multiple `DataSource` beans exist, use `@Qualifier` or the appropriate candidate selection rule.

### 8.1. Lifecycle callbacks do not apply automatically to directly called objects

Suppose a factory method:

```java
@Bean(initMethod = "start", destroyMethod = "stop")
VendorClient vendorClient() {
    return new VendorClient();
}
```

`VendorClient` is a hypothetical class with `start()`/`stop()`. Spring invokes init/destroy callbacks for **the instance created and managed by BeanFactory**. If lite-mode code calls `vendorClient()` manually, the method body returns a new `VendorClient` yet **the container does not automatically register that extra object as a bean with those callbacks**. Consequently, the resource may not be started properly or stopped when the context closes.

For external SDKs, especially connection pools/threaded clients, use parameter injection and define resource ownership clearly.

### 8.2. Proxies and AOP can be bypassed

When a target bean is wrapped in a Spring proxy, looking it up via the context normally returns the proxy. Calling the factory method directly in lite mode creates a raw object that never passes through the auto-proxy creator via the registered bean path. Calling business methods on that raw object can skip transactions/caching/metrics depending on configuration.

This is a **distinct yet related issue** to Spring AOP self-invocation:

- **Inter-bean call:** a `@Bean` method calling another `@Bean` factory method; full configuration CGLIB has its own interception mechanism.
- **AOP self-invocation:** a business method `this.inner()` calling another method on the same service; in standard proxy mode it can bypass AOP advice.

Both mechanisms involve proxies, yet **must not be equated** or have one's rules substituted for the other.

## 9. When Is @Configuration(proxyBeanMethods=false) a Good Choice?

This is not an option that "breaks Spring if enabled". It is a valid design choice when factory methods are independent and **do not need inter-bean Java calls**.

Example:

```java
@Configuration(proxyBeanMethods = false)
class ApplicationConfig {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    GreetingService greetingService(Clock clock) {
        return new GreetingService(clock);
    }

    @Bean
    AuditService auditService(GreetingService greetingService) {
        return new AuditService(greetingService);
    }
}
```

This is a structural example with application-defined `GreetingService` and `AuditService`. Every dependency flows through factory method parameters. Benefits include:

- Avoiding dynamic CGLIB subclasses for configurations acting purely as factories.
- Allowing configuration classes to be `final` where appropriate.
- Simplifying semantics: a direct method call is always a direct method call; bean lookup is always via the container.
- Making the dependency graph easy to read from signatures.
- Reducing hidden behavior caused by one method in a class calling another.

However, `false` is not automatically better than `true` for all codebases. An older configuration relying on inter-bean calls must be refactored before switching; otherwise extra out-of-container objects can be created.

### 9.1. Do not flip the flag as a "blind optimization"

Before replacing:

```java
@Configuration
class OldConfig { ... }
```

with:

```java
@Configuration(proxyBeanMethods = false)
class OldConfig { ... }
```

read every factory method in that class to look for direct calls to other `@Bean` methods, external calls into the configuration bean, or assumptions about scope/lifecycle.

If any exist, convert them to method parameter injection first and add **identity/lifecycle/proxy** tests. Only then consider disabling interception.

## 10. Boundaries: Where Are Direct Calls Intercepted?

### 10.1. Inside the full @Configuration class itself

The common Spring-guaranteed case: an instance `@Bean` method calling another instance `@Bean` method on the **enhanced configuration bean**. Spring routes the reference to the managed bean per scope.

### 10.2. From outside, through Spring's configuration bean

```java
FullConfig config = context.getBean(FullConfig.class);
Widget widget = config.widget();
```

This snippet is based on the runnable example in section 6. `config` is the Spring-managed and enhanced instance; therefore `widget()` can be intercepted as shown by `full.externalCallManaged=true`.

Even so, calling configuration `@Bean` methods from business code couples architecture to the factory; constructor injection of `Widget` into consumers is still preferable.

### 10.3. From an object instantiated with new outside Spring

```java
FullConfig config = new FullConfig();
Widget widget = config.widget();
```

This is a Java direct call on an unenhanced object, so the method body runs normally. Do not confuse "a class annotated with `@Configuration`" with "every instance of that class is proxied by Spring".

### 10.4. Static @Bean methods

```java
@Configuration
class SettingsConfig {
    @Bean
    static Settings settings() {
        return new Settings();
    }

    @Bean
    Client client() {
        return new Client(settings());
    }
}
```

`Settings` and `Client` are illustrative types. Static methods cannot be overridden by CGLIB, so `settings()` inside `client()` is a regular Java call, even when the configuration class is in full mode.

Refactor to `Client client(Settings settings)` so Spring supplies the registered bean.

### 10.5. Other @Configuration classes

If another config class obtains the **managed enhanced bean** of a full configuration and invokes an eligible method, interception can still apply. Yet **calling `new OtherConfig().beanMethod()`** lacks that infrastructure.

In practice, wiring dependencies via factory method parameters, `@Import`, and bean injection is far cleaner than passing configuration classes around just to call factories.

### 10.6. @Bean methods on plain @Component

`@Bean` methods of a plain `@Component` class (lite mode) do not have CGLIB inter-bean call interception with full `@Configuration` semantics, even when the component instance is managed by Spring. Thus **managed component** and **enhanced configuration** are not the same thing.

## 11. Bean Names, @Qualifier, and @Primary When Switching to Parameter Injection

If a configuration defines two beans of the same type:

```java
@Bean("primaryClock")
Clock primaryClock() {
    return Clock.systemUTC();
}

@Bean("testClock")
Clock testClock() {
    return Clock.fixed(
            java.time.Instant.parse("2024-01-01T00:00:00Z"),
            java.time.ZoneOffset.UTC
    );
}
```

This snippet belongs inside a configuration class and requires importing `java.time.Clock`. Directly calling `primaryClock()` in another factory method can be intercepted in full mode, yet in lite mode runs the method body like plain Java. The consistent solution:

```java
@Bean
TimeReporter timeReporter(
        @Qualifier("primaryClock") Clock clock) {
    return new TimeReporter(clock);
}
```

`TimeReporter` is a hypothetical business type; requires importing `org.springframework.beans.factory.annotation.Qualifier`. Spring resolves the right candidate by qualifier and scope. If a real application has a default bean, `@Primary` can help disambiguate by-type dependencies, though qualifiers remain clearer when business logic requires a specific name.

Do not rely on calling a `@Bean` method by name as an implicit strategy for selecting beans once the codebase chooses lite mode. **Place selection criteria directly at the injection point**.

## 12. Circular Dependencies and Inter-Bean Calls

Sometimes learners use inter-bean calls to wire a dependency cycle:

```java
@Bean
A a() {
    return new A(b());
}

@Bean
B b() {
    return new B(a());
}
```

`A` and `B` are hypothetical business types. This is a constructor dependency cycle. Full-mode interception **does not automatically break cycles**: BeanFactory can detect that a bean is being requested while already in creation and throw a circular-reference/bean-currently-in-creation error.

Lite mode risks even worse infinite Java recursion between `a()` and `b()`, bypassing BeanFactory's expected cycle checks.

You must redesign the dependency: split responsibilities, extract an interface, run post-initialization setup where valid, use events, or intentionally use providers/lazy lookups. Never use direct `@Bean` method calls to dodge container cycle detection.

### 12.1. Calling the same method within its own body

If a factory method calls itself:

```java
@Bean
A a() {
    return a();
}
```

This is a design-invalid example: in full mode, Spring can hit a bean-currently-in-creation error; in lite mode it recurses endlessly. Completely avoid calling a factory method inside itself to declare dependencies.

## 13. Inter-Bean Calls and Initialization Timing

`@Bean` methods are parsed by Spring into bean definitions before most regular singletons are created. When full config intercepts `b()` from `a()`, it can **trigger bean `b` to be created earlier** if it does not yet exist.

This does not mean Spring always creates beans strictly in source-code order. Spring must account for dependencies, `@Lazy`, bean scopes, post-processors, and numerous lifecycle factors.

### 13.1. @Lazy and lookup

```java
@Bean
@Lazy
ExpensiveClient expensiveClient() {
    return new ExpensiveClient();
}

@Bean
Service service() {
    return new Service(expensiveClient());
}
```

`ExpensiveClient`/`Service` are illustrative types; import `Lazy`. In full mode, if `service` is eagerly initialized and calls `expensiveClient()`, the lookup can force Spring to create `expensiveClient` **immediately to construct `service`**, even though that bean is declared lazy.

In lite mode, the `expensiveClient()` body is invoked directly from `service()`, bypassing the lazy bean definition and creating an extra out-of-container object. Do not treat `@Lazy` on a factory method as a barrier against manual Java calls.

### 13.2. Post-processors and early instantiation

Special beans like `BeanFactoryPostProcessor`/`BeanPostProcessor` may have to be created very early. For static `@Bean` methods providing those processors, Spring usually recommends static factory methods to avoid creating the configuration instance early.

This complements our topic: static `@Bean` methods **do not intercept direct calls**, so do not call a static processor factory merely to grab the processor in business code. Spring needs to discover them by return type and register them in the right phase.

## 14. Example Comparing Object Counts and Lifecycle with External SDKs

Suppose a configuration:

```java
@Configuration(proxyBeanMethods = false)
class VendorConfig {
    @Bean
    VendorClient vendorClient() {
        return VendorClient.create();
    }

    @Bean
    VendorService vendorService() {
        return new VendorService(vendorClient());
    }
}
```

`VendorClient`/`VendorService` and `VendorClient.create()` are a hypothetical SDK. It can create **two clients**: one for the `vendorClient` bean and one from the call inside `vendorService`. If each client spins up a connection pool or background threads, the project can double resource usage and fail to shut down the extra object.

Switch to:

```java
@Configuration(proxyBeanMethods = false)
class VendorConfig {
    @Bean
    VendorClient vendorClient() {
        return VendorClient.create();
    }

    @Bean
    VendorService vendorService(VendorClient vendorClient) {
        return new VendorService(vendorClient);
    }
}
```

Now Spring performs dependency resolution on the managed `VendorClient`. If the SDK client requires `close()`, use `@Bean(destroyMethod="close")` when appropriate per contract and confirm ownership so the container closes the managed resource. Do not assume every SDK client has identical methods/lifecycle.

**Practical test:** inject `VendorClient` into a test bean and verify the reference inside `VendorService` is the exact managed bean, or use a spy/counter/factory test double to assert only one pool is created.

## 15. Common Misunderstandings

### Misunderstanding 1: "@Bean calling another @Bean is always a singleton"

No. Full mode returns beans according to scope: singletons share an instance, prototypes can differ per lookup, and scoped proxies follow their scope. Lite-mode direct calls do not obey container lookup semantics.

### Misunderstanding 2: "proxyBeanMethods=false makes Spring ignore @Bean"

No. Factory methods are still processed to register/create beans. Only **interception of Java calls** is turned off.

### Misunderstanding 3: "With @Configuration, static methods are also intercepted by CGLIB"

No. Static methods cannot be overridden; direct calls to a static factory still execute the body as normal.

### Misunderstanding 4: "@Component containing @Bean behaves like full @Configuration"

No. `@Bean` on a plain `@Component` runs in lite mode. If method A calls method B, it is a direct Java call, not a container lookup.

### Misunderstanding 5: "If the object from a direct call has the same class, it's also a Spring bean"

No. A Spring bean is defined by **its bean definition and container management**. An object of the same class created outside does not receive DI, post-processing, init/destroy callbacks, or proxies.

### Misunderstanding 6: "Changing true to false to optimize is completely safe"

No. Before changing, find all direct calls between `@Bean` methods and from outside into the config bean, and convert them to parameter injection or proper container lookups.

### Misunderstanding 7: "Getting a new prototype via a direct call is identical to getting a prototype bean"

No. Even though a new instance is returned, a direct call skips lifecycle/proxies/dependency resolution tied to the bean definition; only container lookups truly obey scope.

### Misunderstanding 8: "Calling new FullConfig() still keeps CGLIB active"

No. Enhancement lives on the Spring-managed config bean; manually constructed objects via `new` are not replaced by Spring's enhanced subclass.

### Misunderstanding 9: "Full interception solves constructor circular dependencies"

No. Circular dependencies remain a design flaw and do not vanish thanks to CGLIB method interception.

### Misunderstanding 10: "Calling @Bean methods in business code is valid DI"

Normally no. Consumers should receive dependencies via constructors; factory methods and configuration classes belong to the wiring/composition layer, not a service locator for business code.

### Misunderstanding 11: "Spring definitely creates beans in source-code method order"

Do not rely on source order as a contract. Dependency graphs, `@Lazy`, bean scopes, post-processors, and bean definition ordering all affect timing; use cases must be valid independent of unguaranteed order.

### Misunderstanding 12: "Method parameter injection only works when proxyBeanMethods=true"

No. Parameter injection is standard Spring dependency resolution, works smoothly in both full and lite modes, and is the recommended style when interception is disabled.

## 16. Testing Checklist Before Switching to Lite Mode

Before setting `@Configuration(proxyBeanMethods=false)` in a real project:

1. **Locate configuration:** is the class genuinely registered with Spring or just a manually constructed Java object?
2. **List factory methods:** which methods carry `@Bean`, and which directly call another method?
3. **Identify direct inter-bean calls:** `beanB()` inside `beanA()`, calls from helper methods, calls from other configuration classes, or calls through a managed config bean.
4. **Fix dependency expression:** turn direct calls into factory method parameters, adding qualifiers where needed.
5. **Check scope:** do singleton, prototype, request/session, and lazy behaviors still hold?
6. **Check identity:** does the object in the consumer match the managed singleton returned by the container?
7. **Check lifecycle:** are init/destroy callbacks, proxying, autowiring, and resource cleanup applied to the right instance?
8. **Check expensive resources:** is only one connection pool/HTTP client/mapper created per policy?
9. **Check static methods:** do not expect interception for static `@Bean`s.
10. **Check test code:** tests constructing configurations via `new` do not simulate a full Spring context.
11. **Run integration tests:** use `AnnotationConfigApplicationContext` or the real context to assert the bean graph.
12. **Watch warnings:** if bean creation/processor warnings appear after refactoring, never ignore them thinking "we only flipped a flag".

## 17. Quick Ways to Test and Investigate Duplicate Bean Creation

### 17.1. Counting factory body invocations

In a test fixture, use an `AtomicInteger` incremented when the factory method actually returns an object:

```java
private final AtomicInteger created = new AtomicInteger();

@Bean
Widget widget() {
    return new Widget(created.incrementAndGet());
}
```

This snippet is based on `Widget` from the demo; to run standalone, it needs a containing class with bean definitions and imports. Comparing counters when creating full vs. lite contexts reveals whether direct calls execute the body.

### 17.2. Checking identity

```java
Widget managed = context.getBean(Widget.class);
Pair pair = context.getBean(Pair.class);

System.out.println(pair.first() == managed);
System.out.println(pair.first() == pair.second());
```

This snippet fits within the example's context scope. When singletons resolve properly, the references match. In lite mode with direct calls inside factory bodies, they can differ.

### 17.3. Inspecting bean definitions

```java
var factory = context.getBeanFactory();
var def = factory.getBeanDefinition("widget");

System.out.println(def.getFactoryMethodName());
System.out.println(factory.containsSingleton("widget"));
```

Snippet requires an `AnnotationConfigApplicationContext`. `getFactoryMethodName()` is normally `widget` in the example; `containsSingleton("widget")` only reports whether the singleton cache holds an instance. It **cannot detect extra objects** created outside the container via direct Java calls. Combine bean definition checks with factory-body counters and identity assertions to diagnose.

### 17.4. Testing with mocks/spies

If a library returns an object holding sockets/threads where direct identity comparison is inconvenient in tests, wrap creation in a spy-friendly factory or use an independent provider/test counter. Assert invariants:

- Number of factory invocations per policy.
- Consumer bean receives the exact managed dependency.
- Context shutdown closes Spring-owned resources and does **not** close externally owned objects.
- Two connection pools/clients are never created unexpectedly.

You do not need to mock Spring's internal CGLIB interceptor directly; testing observable behavior is more stable and useful.

## 18. Exercises and Answers

**Question 1.** In full `@Configuration`, `@Bean A a()` calls `b()` twice; `b` is a singleton. Are the two results always two different objects?

**Answer:** No. For eligible calls intercepted through the enhanced configuration, both lookups normally return the same managed `b` singleton.

**Question 2.** Replace full config with `@Configuration(proxyBeanMethods=false)` while keeping `b()` calls inside `a()`. What changes?

**Answer:** `b()` becomes a regular Java call, executing the factory body each time and creating objects outside the `b` bean Spring manages.

**Question 3.** How do you rewrite `a()` to use the proper singleton in lite mode?

**Answer:** `@Bean A a(B b) { return new A(b); }`. Spring resolves the dependency parameter according to the bean definition/scope.

**Question 4.** If bean `b` is a prototype in full mode, do two cross-calls through the enhanced configuration return the same instance?

**Answer:** No. Each container lookup for a prototype normally produces a new instance per scope, so the two results can differ.

**Question 5.** Why is a static `@Bean` not intercepted, even in full configuration?

**Answer:** CGLIB uses subclassing and method overriding; static Java methods cannot be overridden.

**Question 6.** If Spring has registered bean `clock`, does `new MyConfig().clock()` retrieve that singleton?

**Answer:** No. A configuration object constructed manually outside the container is not enhanced; the method call is plain Java.

**Question 7.** Why can a `new VendorClient()` call in lite config cause a resource leak?

**Answer:** If called from another factory method, the extra object may not be registered as a bean and will not receive the managed `VendorClient`'s destroy callback. Inject the client from the container instead.

**Question 8.** Do `@Bean` methods in a plain `@Component` get full inter-bean interception?

**Answer:** No. That is lite mode, so cross-calls are not routed to Spring-managed lookups.

**Question 9.** Should you use `@Primary` instead of `@Bean` parameters when switching to lite mode?

**Answer:** `@Primary` solves by-type candidate selection; it does not make a direct Java call intercepted. Parameter injection is still required, with qualifiers if a specific bean must be chosen.

**Question 10.** Why can a test using `new FullConfig()` give different results from a test creating `AnnotationConfigApplicationContext(FullConfig.class)`?

**Answer:** Only the real context creates/enhances the configuration bean and intercepts bean lookups. Objects constructed with `new` have no CGLIB enhancement.

**Question 11.** A singleton service needs a fresh prototype on every business request. Should it call the `prototypeBean()` factory method directly from the service?

**Answer:** No. Inject `ObjectProvider<PrototypeType>` or an equivalent lookup mechanism, and request a new bean from the container at the proper time.

**Question 12.** Should you change every `@Configuration` class to `proxyBeanMethods=false` without testing?

**Answer:** No. It is safe only when nothing relies on inter-bean interception and scope/identity/lifecycle/proxy behaviors have been verified.

## 19. Official References

- [Spring Framework 6.2 — Basic Concepts: @Bean and @Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/basic-concepts.html): full `@Configuration` and lite `@Bean`, warnings on cross-method calls without proxying.
- [Spring Framework 6.2 — Using the @Configuration Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/configuration-annotation.html): inter-bean dependencies, CGLIB subclassing, scope rules, and final-method limits.
- [Spring Framework 6.2 — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html): factory methods, return types, lifecycle, and scopes.
- [Spring Framework 6.2 API — Configuration](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/annotation/Configuration.html): `proxyBeanMethods` and full/lite semantics.
- [Spring Framework 6.2 API — Bean](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/annotation/Bean.html): inter-bean references, static `@Bean` methods, scope, and lifecycle.
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): singleton, prototype, and other scopes.

**Core takeaway:** In full `@Configuration(proxyBeanMethods=true)`, calls to **instance `@Bean` methods** on the Spring-enhanced configuration are routed through the BeanFactory to obey bean scope and lifecycle. In lite mode (`proxyBeanMethods=false` or `@Bean` on plain `@Component`), the same call is ordinary Java. **`@Bean` method parameters are the clearest, safest, and least mode-dependent way to express dependencies.**
