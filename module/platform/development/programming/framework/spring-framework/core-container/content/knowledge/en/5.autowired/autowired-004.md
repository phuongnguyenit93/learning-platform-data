# Field, Setter, and Multi-Parameter Method Injection with `@Autowired`

## 1. Objectives and Scope

The Spring Core Container can supply dependencies automatically to a container-managed object through multiple injection points. This article focuses on three styles of using `@Autowired` on an **instance field**, a **JavaBean setter**, and an **arbitrarily named method accepting multiple parameters**. These are related mechanisms yet differ significantly in injection timing, object state, missing-dependency handling, and testability.

After studying this, you will be able to:

1. Correctly write and read `@Autowired` on a `private` field, a `setX(...)` setter, and a `configure(A, B, ...)` method.
2. Explain why both **field and method injection** occur **after the Java constructor runs**; Spring performs them when creating a **Spring-managed bean**, not automatically on an arbitrarily `new`'d object.
3. Distinguish a multi-parameter method with `required=true` (default) from `@Autowired(required=false)` and an `Optional<T>` parameter.
4. Know how Spring selects beans by type, qualifier, primary, and handles missing or multiple candidates.
5. Directly observe **a field-injected bean, a setter-injected bean, and a two-parameter method-injected bean**, with dedicated examples for optional multi-parameter methods.
6. Use Java 17+, Maven, and Spring Framework 7.0.9 with deterministic run commands and expected stdout.

**Scope:** Pure Spring Framework Core Container only; no Spring Boot, HTTP server, database, `@SpringBootApplication`, or auto-configuration. Specific Java constructor injection rules are only compared when they clarify the three main injection styles.

## 2. Three Mechanisms Side by Side

| Injection Style | Annotation Example | Parameters | Timing | Design Consequence |
| --- | --- | --- | --- | --- |
| **Field** | `@Autowired private Gateway gateway;` | No method parameters | **After construction**, when Spring populates fields | Very concise, but dependencies are hidden from the constructor; unnatural with `final` |
| **Setter** | `@Autowired void setGateway(Gateway g)` | Typically one | **After construction**, Spring resolves the argument and calls the setter | Sensible for properties with default values/reconfiguration; mutable reference if setter is public |
| **Arbitrary method** | `@Autowired void prepare(Gateway g, Formatter f)` | **One or more**, any name | **After construction**, Spring resolves **the parameters** then invokes the method | Can configure multiple dependencies in one intentional operation |
| Constructor (for comparison) | `@Autowired Service(Gateway g)` or a single unannotated constructor | One or more | **Before/during construction** | Explicit contract, supports `final` fields, convenient for unit testing |

Common point of confusion: **setter injection is not a special Spring system separate from method injection**. A setter `setGateway(Gateway)` is a **special case** of a configuration method that Spring can invoke. `@Autowired` does not require the method to be named `set...`, and a multi-parameter method can be named `initializeClients`, `configure`, `prepare`, or anything else.

All of these forms require a **target bean belonging to the context** and annotation processing infrastructure. By default, `AnnotationConfigApplicationContext` registers essential annotation processors, including `AutowiredAnnotationBeanPostProcessor`. The container must find bean candidates for the injection point before it has a reference to supply.

**`@Autowired` does not automatically create an arbitrary implementation from an interface.** For instance, `@Autowired Gateway gateway` requires a registered and matching `Gateway` bean; if missing, Spring normally fails bean creation rather than doing `new Gateway` itself.

## 3. Field Injection: Concise, But Dependencies Are Hidden

Syntax snippet:

~~~java
// Snippet inside a Spring-managed bean:
@Autowired
private Gateway gateway;

public String route() {
    return gateway.id();
}
~~~

Key points:
- Spring can inject a **private instance field** via appropriate reflection mechanisms. The field needs neither a setter nor `public` visibility; the annotation sits directly on the field.
- Injection occurs **after the constructor creates the instance**. If the constructor reads this field before Spring supplies it, its value will normally still be `null` (unless the class initializes the field itself).
- Requires a **Spring-managed bean**. `new FieldClient()` outside Spring does not trigger `@Autowired`. Without another initial value, using the field then can cause a `NullPointerException`.
- **`final` fields should be assigned in a constructor or initializer in Java**; do not use field injection as a normal way to supply a required dependency into a `final` field.
- `@Autowired` defaults to `required=true`. When no matching candidate exists to inject a required field, bean creation can fail.
- `@Autowired(required=false)` for a genuinely optional field can **skip the assignment**, keeping the field's default value. Do not use this to hide a dependency that is actually required.

**Compared to constructor injection:** A constructor `Service(Gateway gateway)` lets a Java caller pass a fake and keep `private final Gateway gateway`. With field injection, test code calling `new Service()` cannot receive the dependency unless using test seams, reflection, or a real context. Thus constructor injection is usually better suited for **required business dependencies**, while field injection is supported with clear trade-offs to recognize.

**Thread safety:** A field-injected Spring singleton is not automatically thread-safe. Having a reference injected does not make the collaborating object immutable or synchronize its state. If the reference does not need to change after startup, designing with constructor + `final` usually makes invariants clearer.

## 4. Setter Injection: A JavaBean Setter Is a Config Method

Setter injection looks like:

~~~java
// Snippet placed in a class with the Gateway interface.
private Gateway gateway;
private int calls;

@Autowired
public void setGateway(Gateway gateway) {
    this.gateway = gateway;
    calls++;
}
~~~

When Spring creates the bean:
1. The bean's constructor runs.
2. Spring detects the method annotated with `@Autowired`.
3. The bean factory resolves a matching `Gateway` dependency.
4. Spring calls `setGateway(resolvedGateway)` **once during normal injection**.
5. Business code can use the configured field once the bean finishes initializing.

The condition is not merely the `set...` name: `@Autowired` is what marks the method as an injection point. If a setter is unannotated and not configured for injection via another mechanism, Spring **is not automatically obligated to call it** just because the method starts with `set`.

Setters can be `public`, `protected`, or non-public when environment accessibility permits. The standalone runnable examples below use `public` methods for easy observation. In JPMS applications using the Java module path, `opens`/reflection requirements must be checked; this article runs on the standard classpath.

### When Are Setters Useful?

- A **genuinely optional** dependency with valid default behavior.
- Configuring initialization of an existing legacy class whose constructor cannot be modified.
- A property that can be re-adjusted via a public API under an explicit contract.

However, **exposing a setter for a required dependency** lets Java callers create the bean in an incomplete state, and other callers may swap the reference later. For a singleton accessed across multiple threads, mutating a dependency without proper synchronization introduces risk.

**Why can it fail at startup?** If a setter is annotated with default required `@Autowired` and no matching `Gateway` bean exists, Spring normally fails to finish creating the bean. Simply having a single parameter does not turn the setter into optional.

## 5. Multi-Parameter Methods: All Dependencies Resolved Before Invocation

Spring supports configuration methods with any name:

~~~java
// Snippet: Gateway and Formatter are interfaces in the demo.
private Gateway gateway;
private Formatter formatter;

@Autowired
public void configure(Gateway gateway, Formatter formatter) {
    this.gateway = gateway;
    this.formatter = formatter;
}
~~~

With the method above, Spring must find **both Gateway and Formatter** before invoking `configure(...)`. If the injection point is required and a required parameter is missing, bean creation can fail; the method is never successfully called with a "half-populated" argument list.

A single method can be used to set **a group of related dependencies**; for example, a gateway and formatter collaborating in one configuration unit. If they are not closely related in business terms, stuffing 12 parameters into one method to dodge a long constructor does not solve the class having too many responsibilities.

### Method Names and Parameter Counts

- `configure(Gateway, Formatter)` and `setParts(Gateway, Formatter)` can both be processed by Spring if annotated; these are **not** single-parameter JavaBeans setters by convention, yet they are Spring arbitrary config methods.
- `@Qualifier` can be used on **specific parameters** when multiple beans share a type, such as `configure(@Qualifier("primaryGateway") Gateway g, Formatter f)`.
- `@Autowired` on the **method declaration** drives method injection. Putting `@Autowired` separately on individual parameters is not the normal way to have the Core Container invoke that method automatically.
- Non-public methods can still be supported depending on accessibility, though avoid designs heavily reliant on reflection when targeting the module path.
- `static` methods are not normal targets for instance autowiring; dependencies belong on bean instances rather than global static state.

**Ordering:** `AutowiredAnnotationBeanPostProcessor`'s Javadoc describes field injection as being processed after construction and before autowired config methods. Do not rely on an **absolute ordering among multiple independent methods** on the same bean when designing business rules; if initialization work must run **after all injections**, use an appropriate lifecycle callback.

## 6. `required=false`: Multi-Parameter Method Is Skipped Entirely

This is a particularly important difference between **method injection** and what many people assume about null:

~~~java
// Snippet: Gateway has a bean, but Telemetry may be absent.
@Autowired(required = false)
public void attach(Gateway gateway, Telemetry telemetry) {
    // Runs only if all required parameters are resolved.
}
~~~

If the context has `Gateway` yet **lacks `Telemetry`**, Spring **does not call `attach`**. It does not call `attach(gateway, null)`. The `required=false` attribute here applies to the **method's injection point**, meaning when any needed dependency cannot be satisfied, the **entire method may be skipped**. This matches Spring Framework documentation: a non-required method is not invoked if one of its dependencies is missing.

| Scenario | Required `@Autowired` Method | `@Autowired(required=false)` Method |
| --- | --- | --- |
| Both Gateway and Telemetry present | Spring resolves and calls the method | Spring resolves and calls the method |
| Gateway present, Telemetry missing | Typically fails bean creation | **Skips the entire method**, no partial assignment |
| Neither present | Typically fails bean creation | **Skips the entire method** |
| Multiple Gateway candidates, cannot disambiguate | Can fail due to ambiguity | Should not treat `required=false` as an arbitrary picker or a way to hide conflicts |

In multi-parameter methods that need both **to run when dependency A is present** and **tolerate missing B**, consider expressing parameter B individually as `Optional<B>` (or using a provider/default strategy). That differs clearly from marking the **entire method** non-required.

Example:

~~~java
@Autowired
public void observe(
        Gateway gateway, Optional<Telemetry> telemetry) {
    // Method is still called when Gateway is present, even if telemetry = Optional.empty().
}
~~~

Even though `Optional<T>` can represent absence, **do not use Optional to turn a genuinely required business dependency into an optional one**. When a missing `Gateway` makes operation impossible, let the context fail fast rather than silently running in an invalid mode.

## 7. Resolving Multiple Candidates, Qualifiers, Collections, and Nullability

### One Type with Multiple Beans

If both `fastGateway` and `safeGateway` implement `Gateway`, an injection point declaring only `Gateway` can be ambiguous:

~~~java
// Snippet applicable to an arbitrary config method:
@Autowired
public void configure(
        @Qualifier("fastGateway") Gateway gateway,
        Formatter formatter) {
    // ...
}
~~~

Requires importing `org.springframework.beans.factory.annotation.Qualifier` and registering matching bean names/qualifiers. `@Qualifier` helps **filter candidates**; it neither creates a `Gateway` nor changes Java types. `@Primary` can designate bean preference when resolving a single-valued dependency under appropriate conditions.

**Do not assert that Spring always looks up by field name first and then by type**. Spring resolution is primarily type-based, combined with qualifier/primary metadata, generics, and other rules. Matching a field/parameter name with a bean name can play a role, yet it should not replace an explicit selection contract when multiple implementations exist.

### Injecting Multiple Beans at Once

Spring also supports:
- `List<Gateway>` or `Gateway[]` to receive matching beans (ordering rules can be influenced by `@Order`/`Ordered`).
- `Map<String, Gateway>` using **bean names** as keys.
- Required collection injection points have specific rules per case; do **not** assume missing beans always yield an empty collection, especially compared to special constructor/factory method cases.

### Per-Parameter Optionality

`Optional<T>` at an injection point expresses bean absence. `ObjectProvider<T>` is a Spring API for **on-demand lookup**, where `getIfAvailable()` differs from `getObject()`; the latter demands a matching bean and can fail if missing. With `@Autowired(required=false)` on a setter, the entire setter is skipped when the dependency is absent — no `setX(null)` call happens.

`@Nullable` is supported by Spring at injection points through version-appropriate nullability annotations, though the right package/semantics must be chosen. In this article, pure Java 17 `Optional<T>` is used to avoid depending on an additional specific nullability annotation.

## 8. Maven Java 17 Demo: Field, Setter, Multi-Parameter Method, and Optional Method

A single Java 17 project using Spring Framework **7.0.9**. It runs three controlled experiments:

1. **Java `new` outside the container:** `FieldClient`'s `@Autowired` field holds no reference.
2. **Base context:** has `Gateway` and `Formatter`, but **no** `Telemetry`. Spring injects the field, invokes the setter, and invokes the multi-parameter method. The non-required method `attach(Gateway, Telemetry)` **is skipped**, while `observe(Gateway, Optional<Telemetry>)` is still called with empty.
3. **Context with Telemetry:** both dependencies are supplied, so `attach(...)` is invoked; `Optional<Telemetry>` receives the present bean.
4. **Missing required field:** creates a `MissingClient` bean with `@Autowired Telemetry` without declaring `Telemetry`, observing startup rejection.

All classes in the demo are declared in **a single Java file**, making the example self-contained and easy to run. No Spring Boot, web, database, or JUnit required.

### 8.1. Project Structure

~~~text
injection-forms-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── InjectionFormsDemo.java
~~~

Before practicing, verify **JDK 17+**, **Maven 3.9+**, and access to Maven Central/a mirror repository.

### 8.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>injection-forms-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>7.0.9</version>
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
                    <mainClass>demo.InjectionFormsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Maven resolves `spring-context` and foundational Spring artifacts via the dependency graph; there is no need to manually download transitive JARs. `maven.compiler.release=17` targets Java 17, and the Exec Maven Plugin runs the main class with the dependency classpath.

### 8.3. `src/main/java/demo/InjectionFormsDemo.java`

~~~java
package demo;

import java.util.Optional;

import org.springframework.beans.BeansException;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class InjectionFormsDemo {
    private InjectionFormsDemo() {
    }

    @FunctionalInterface
    public interface Gateway {
        String id();
    }

    @FunctionalInterface
    public interface Formatter {
        String format(String name);
    }

    @FunctionalInterface
    public interface Telemetry {
        String id();
    }

    public static final class FieldClient {
        @Autowired
        private Gateway gateway;

        public boolean ready() {
            return gateway != null;
        }

        public String gatewayId() {
            return gateway.id();
        }
    }

    public static final class SetterClient {
        private Gateway gateway;
        private int setterCalls;

        @Autowired
        public void setGateway(Gateway gateway) {
            this.gateway = gateway;
            setterCalls++;
        }

        public int calls() {
            return setterCalls;
        }

        public String gatewayId() {
            return gateway.id();
        }
    }

    public static final class MultiClient {
        @Autowired
        private Gateway fieldGateway;
        private Gateway gateway;
        private Formatter formatter;
        private int methodCalls;
        private boolean fieldReadyDuringMethod;

        @Autowired
        public void configure(Gateway gateway, Formatter formatter) {
            this.fieldReadyDuringMethod = fieldGateway != null;
            this.gateway = gateway;
            this.formatter = formatter;
            methodCalls++;
        }

        public int calls() {
            return methodCalls;
        }

        public boolean fieldReadyDuringMethod() {
            return fieldReadyDuringMethod;
        }

        public String result(String name) {
            return gateway.id() + "|" + formatter.format(name);
        }
    }

    public static final class OptionalClient {
        private int optionalMethodCalls;
        private int observationCalls;
        private boolean telemetryPresent;
        private String state = "default";

        @Autowired(required = false)
        public void attach(Gateway gateway, Telemetry telemetry) {
            optionalMethodCalls++;
            state = gateway.id() + ":" + telemetry.id();
        }

        @Autowired
        public void observe(Gateway gateway, Optional<Telemetry> telemetry) {
            observationCalls++;
            telemetryPresent = telemetry.isPresent();
        }

        public int optionalMethodCalls() {
            return optionalMethodCalls;
        }

        public int observationCalls() {
            return observationCalls;
        }

        public boolean telemetryPresent() {
            return telemetryPresent;
        }

        public String state() {
            return state;
        }
    }

    public static final class MissingClient {
        @Autowired
        private Telemetry telemetry;
    }

    @Configuration(proxyBeanMethods = false)
    public static class BaseConfig {
        @Bean
        public Gateway gateway() {
            return () -> "GW";
        }

        @Bean
        public Formatter formatter() {
            return name -> "Hello," + name;
        }

        @Bean
        public FieldClient fieldClient() {
            return new FieldClient();
        }

        @Bean
        public SetterClient setterClient() {
            return new SetterClient();
        }

        @Bean
        public MultiClient multiClient() {
            return new MultiClient();
        }

        @Bean
        public OptionalClient optionalClient() {
            return new OptionalClient();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class ExtraConfig {
        @Bean
        public Telemetry telemetry() {
            return () -> "TR";
        }
    }

    public static void main(String[] args) {
        // Plain Java new does NOT run Spring post-processors.
        FieldClient plain = new FieldClient();
        System.out.println("manual.field.ready=" + plain.ready());

        // Gateway and Formatter are present, but NO Telemetry.
        try (var base =
                new AnnotationConfigApplicationContext(BaseConfig.class)) {
            FieldClient field = base.getBean(FieldClient.class);
            SetterClient setter = base.getBean(SetterClient.class);
            MultiClient multi = base.getBean(MultiClient.class);
            OptionalClient optional = base.getBean(OptionalClient.class);

            System.out.println("base.field.ready=" + field.ready());
            System.out.println("base.field.gateway=" + field.gatewayId());
            System.out.println("base.setter.calls=" + setter.calls());
            System.out.println("base.setter.gateway=" + setter.gatewayId());
            System.out.println("base.multi.calls=" + multi.calls());
            System.out.println("base.multi.fieldBeforeMethod="
                    + multi.fieldReadyDuringMethod());
            System.out.println("base.multi.value=" + multi.result("Lan"));
            System.out.println("base.optional.calls="
                    + optional.optionalMethodCalls());
            System.out.println("base.optional.state=" + optional.state());
            System.out.println("base.optional.observeCalls="
                    + optional.observationCalls());
            System.out.println("base.optional.telemetryPresent="
                    + optional.telemetryPresent());
        }

        // Adding Telemetry, all injection points are satisfied.
        try (var with = new AnnotationConfigApplicationContext(
                BaseConfig.class, ExtraConfig.class)) {
            OptionalClient optional = with.getBean(OptionalClient.class);

            System.out.println("with.optional.calls="
                    + optional.optionalMethodCalls());
            System.out.println("with.optional.state=" + optional.state());
            System.out.println("with.optional.observeCalls="
                    + optional.observationCalls());
            System.out.println("with.optional.telemetryPresent="
                    + optional.telemetryPresent());
            System.out.println("with.optional.singleton="
                    + (optional == with.getBean(OptionalClient.class)));
        }

        // Required field missing bean: refresh() fails.
        try (var missing = new AnnotationConfigApplicationContext()) {
            missing.register(BaseConfig.class);
            missing.registerBean(MissingClient.class);
            missing.refresh();
        } catch (BeansException expected) {
            System.out.println("missingRequired.failed=true");
        }
    }
}
~~~

### 8.4. Code Explanation Across the Three Injection Styles

- **FieldClient:** the `private Gateway gateway` field has `@Autowired`, and Spring populates the `Gateway` bean after construction. For a `new FieldClient()` object outside Spring, `ready() == false`.
- **SetterClient:** the `setGateway(Gateway)` method is annotated. The `setterCalls` counter confirms the method is called by Spring **once** during bean creation in the example. The method can also be called by normal Java code if a caller invokes it directly; the annotation is not exclusive to Spring.
- **MultiClient:** the `configure(Gateway,Formatter)` method is not named `set...` yet is still an injection point. Spring resolves both parameters. `fieldGateway` is field-injected before the config method under this mechanism, so the `fieldReadyDuringMethod` flag is `true`.
- **OptionalClient:** `attach(Gateway,Telemetry)` is marked `required=false`. In the base context with only `Gateway`, Spring **skips the entire method**, leaving `state="default"` and `optionalMethodCalls=0`. However, `observe(Gateway,Optional<Telemetry>)` is still invoked; the optional parameter is empty.
- **ExtraConfig:** adding `Telemetry`, this time `attach` runs once and `observe` receives `Optional.of(...)`. The two methods do not depend on **ordering between them**, so the final outcome is deterministic.
- **MissingClient:** has one required `Telemetry` field, registered separately in a context lacking `Telemetry`. `refresh()` can throw `BeansException`; the demo catches it and prints a single confirmation line of failure.

`BaseConfig` uses `@Bean` factory methods returning Java objects. **Beans returned by `@Bean` are still post-processed by Spring**, so `@Autowired` fields/methods are handled even though `FieldClient` carries no `@Component`.

`@Configuration(proxyBeanMethods=false)` fits because the factory methods do not invoke each other directly. Do not modify `BaseConfig` to call `gateway()` from other factory methods and assume it returns the same Spring singleton: with proxy mode disabled, ordinary Java calls can create distinct objects.

## 9. CLI Run and Expected Stdout

Inside the `injection-forms-demo` directory containing `pom.xml`, run:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

The three environment check commands produce output dependent on OS, JDK, and Maven. The last command compiles with `javac` via the Maven Compiler Plugin, then runs `demo.InjectionFormsDemo` with the Spring classpath.

**18 deterministic stdout lines produced directly by `System.out.println` statements in `main`** (excluding Maven or Spring logs/diagnostics):

~~~text
manual.field.ready=false
base.field.ready=true
base.field.gateway=GW
base.setter.calls=1
base.setter.gateway=GW
base.multi.calls=1
base.multi.fieldBeforeMethod=true
base.multi.value=GW|Hello,Lan
base.optional.calls=0
base.optional.state=default
base.optional.observeCalls=1
base.optional.telemetryPresent=false
with.optional.calls=1
with.optional.state=GW:TR
with.optional.observeCalls=1
with.optional.telemetryPresent=true
with.optional.singleton=true
missingRequired.failed=true
~~~

**Groups of observations to grasp:**

| Stdout Line | Proof |
| --- | --- |
| `manual.field.ready=false` | Standalone Java `new` does not trigger autowiring |
| `base.field.ready=true`, `gateway=GW` | Spring supplies the bean into the private instance field |
| `base.setter.calls=1` | Spring calls the `@Autowired` setter method during bean creation |
| `base.multi.calls=1`, `multi.value=GW|Hello,Lan` | Arbitrarily named method accepts **two dependencies** and computes result |
| `base.multi.fieldBeforeMethod=true` | Field injection ran before this bean's autowired config method |
| `base.optional.calls=0`, `state=default` | Non-required multi-param method **does not run** when Telemetry is missing |
| `base.optional.observeCalls=1`, `telemetryPresent=false` | Required method still runs thanks to `Optional.empty()` on the optional parameter |
| `with.optional.calls=1`, `state=GW:TR` | Once all dependencies are present, the non-required method is invoked |
| `with.optional.telemetryPresent=true` | `Optional<Telemetry>` holds the present bean |
| `with.optional.singleton=true` | `OptionalClient` is a singleton in the second context |
| `missingRequired.failed=true` | Missing required field causes bean creation failure rather than silently assigning null |

**Do not record fixed exception logs** for the `missing` context: Spring may log a warning on startup failure, with stack traces/messages varying by version/logging. Expected output consists only of the lines intentionally printed by application source code.

## 10. Plain Java `javac`/`java`: Creating the Object and Supplying Parameters Manually

Both field and method injection correspond to ordinary Java: **an object is created, then the caller assigns fields/invokes setters or config methods**. Spring automates looking up beans and invoking the injection points, whereas plain Java must do that with explicit code.

Create a separate file `PureInjectionTypes.java`:

~~~java
public class PureInjectionTypes {
    interface Gateway {
        String id();
    }

    interface Formatter {
        String format(String name);
    }

    static final class Client {
        Gateway field;
        Gateway setterGateway;
        Gateway multiGateway;
        Formatter formatter;
        int setterCalls;

        void setGateway(Gateway gateway) {
            setterGateway = gateway;
            setterCalls++;
        }

        void configure(Gateway gateway, Formatter formatter) {
            multiGateway = gateway;
            this.formatter = formatter;
        }

        String multiResult(String name) {
            return multiGateway.id() + "|" + formatter.format(name);
        }
    }

    public static void main(String[] args) {
        Client client = new Client();
        System.out.println("before.manual.field="
                + (client.field != null));

        Gateway gateway = () -> "G";
        Formatter formatter = name -> "Hi," + name;

        client.field = gateway;
        client.setGateway(gateway);
        client.configure(gateway, formatter);

        System.out.println("after.manual.field="
                + (client.field != null));
        System.out.println("after.manual.setter.calls="
                + client.setterCalls);
        System.out.println("after.manual.multi="
                + client.multiResult("Lan"));
    }
}
~~~

Compile with **JDK 17+** in the directory containing the file, without Maven or Spring:

~~~bash
javac PureInjectionTypes.java
java PureInjectionTypes
~~~

Exact stdout:

~~~text
before.manual.field=false
after.manual.field=true
after.manual.setter.calls=1
after.manual.multi=G|Hi,Lan
~~~

The example demonstrates that setters and multi-parameter methods are **ordinary Java calls**. Spring adds the ability to resolve dependencies from the context. Simply creating a Java object with setters does not make Spring auto-inject it; the object must belong to the bean registration/management mechanism.

## 11. Common Errors and Diagnosing at the Right Layer

| Symptom | Likely Cause | How to Verify |
| --- | --- | --- |
| `@Autowired` field stays null after `new` | Object is **outside the Spring container** | Use constructor injection in tests or fetch the bean from context |
| Using field inside constructor causes NPE | Injection happens **after construction** | Move the required dependency to the constructor |
| Spring reports no `Gateway` bean | No matching bean registered in context | Check `@Bean`, scan, qualifiers, context scope |
| Spring reports multiple `Gateway` candidates | Ambiguous type | Use explicit `@Primary`/`@Qualifier` |
| Setter is not called | Missing injection annotation/config, or non-required method skipped | Verify injection metadata and available candidates |
| Required setter fails at startup | Missing a required dependency | Read `UnsatisfiedDependencyException` and `Caused by` |
| Multi-method skipped even though param A exists | Uses `required=false` but still missing param B | All arguments must resolve for the method to be called |
| Want method to run even if B is absent | Required `B` was modeled incorrectly | Use `Optional<B>`/provider or a domain default |
| Same method runs twice unexpectedly | Test/caller may invoke the method directly as well; check bean lifecycle/registration | Distinguish direct Java calls from Spring injection calls |
| `@Autowired` static field does not work | Static injection is not a supported mechanism | Put dependencies in bean instances, eliminate global mutable state |
| Private field on Java module path blocked from reflection | Module/package does not allow reflective access | Check `opens` and module setup; classpath demo does not hit this |
| `@Autowired(required=false)` yet code still NPEs | Field/method was skipped but business code lacks a valid default | Design true optionality, check null/Optional, or use a no-op implementation |
| Bean created too early before processors | Custom factory/post-processor creates abnormal lifecycle | Inspect registration order and `BeanPostProcessor`s |
| `mvn` fails to resolve `spring-context` | Artifact/repository/JDK/proxy | Check POM GAV, `mvn -version`, Maven Central/mirror |

**Do not confuse a missing bean with a missing JAR:** a missing package at compile time is a build classpath issue; `NoSuchBeanDefinitionException` or `UnsatisfiedDependencyException` in Spring is a graph/configuration issue. If a factory method throws an exception, read the root cause instead of just looking at the "autowire error" label.

### Notes When Using XML or Mixed Configuration

`@Autowired` works thanks to bean post-processors. `AnnotationConfigApplicationContext` registers standard processors; a manually configured XML context may need annotation configuration enabled, such as `<context:annotation-config/>`. XML property injection can have its own ordering/precedence when mixing annotations and explicit property values; avoid putting two conflicting configurations on the same property without good reason.

Custom **`BeanPostProcessor` and `BeanFactoryPostProcessor`** classes you write yourself also have a special lifecycle. Do not assume `@Autowired` inside those processors themselves is handled like ordinary application beans; Spring documentation recommends configuring processor dependencies via explicit factory methods or XML.

## 12. Predict-Then-Verify Exercises

Keep a copy of the original source for comparison; for each experiment, edit a copy and restore the code before moving to the next experiment.

1. **Remove `@Autowired` on `FieldClient`:** predict `base.field.ready` and what happens when calling `gatewayId()`. Why does `@Bean` create `FieldClient` without injecting the field?
2. **Add a second setter:** write an `@Autowired` `setFormatter(Formatter)` method in `SetterClient`, add a field and counter; verify the method is called at bean creation.
3. **Rename `MultiClient.configure` to `prepareComponents`:** does output logic stay the same? Why does the method name not determine autowiring capability?
4. **Remove the `Formatter` bean:** predict `MultiClient`'s required method fails at bean creation rather than receiving `null`.
5. **Add only `Telemetry` to the context:** predict `optionalMethodCalls=1` and `telemetryPresent=true` in `OptionalClient`.
6. **Remove `Telemetry` yet still want the method to run:** change `attach(Gateway, Telemetry)` to `attach(Gateway, Optional<Telemetry>)` and drop `required=false`; handle empty inside the method.
7. **Add two `Gateway` beans:** intentionally cause ambiguity, pick one using `@Primary` or place `@Qualifier("mainGateway")` on the **method parameter**.
8. **Move `Gateway` into the constructor:** refactor `FieldClient` to accept `Gateway` via constructor and make the field `final`, write a plain Java test using `new FieldClient(fake)`. Compare with field injection.
9. **Create bean via component scan:** put `@Component` on `MultiClient`, scan the right package instead of using a `@Bean` method, ensuring no two duplicate bean definitions of that type exist.
10. **Non-required method with two parameters:** change `attach` into a three-parameter method where one type has no bean; confirm the whole method is skipped.
11. **Observe lifecycle:** add `InitializingBean.afterPropertiesSet()` to `MultiClient`, verify references are already present before the init callback.
12. **Use a provider:** replace an optional parameter with `ObjectProvider<Telemetry>`, call `getIfAvailable()` to illustrate on-demand lookup.
13. **Pure Java comparison:** edit `PureInjectionTypes` to skip calling `configure`, predict `multiResult` fails due to missing state; Spring required injection catches wiring mistakes earlier during bean creation.
14. **Try two contexts:** create two independent `BaseConfig` contexts, compare `FieldClient` references; a Spring singleton is scoped per bean definition/container, not one instance across the whole JVM.

### Comprehension Checklist

- [ ] Field injection and setter/method injection run **after the constructor** for Spring-managed beans.
- [ ] A setter is a special case of an autowired configuration method.
- [ ] An arbitrary method can have **any name and multiple parameters**.
- [ ] A required multi-argument method requires resolving all required args.
- [ ] A non-required method **is skipped completely** if a needed dependency is unsatisfied; it does not receive half the arguments.
- [ ] `Optional<T>` on a parameter expresses dependency absence differently from `required=false` on the method.
- [ ] Know how to use qualifiers when multiple candidates share a type.
- [ ] Do not confuse `new` outside the context with a Spring-managed bean.
- [ ] Correctly predict the 18 stdout lines of the Maven demo and 4 lines of plain Java.
- [ ] Know to choose constructor injection for required dependencies and avoid overusing mutable setters.

## 13. Summary and Official Documentation

**Brief summary:** Spring supports injecting dependencies into **fields**, **setters**, and **multi-parameter methods** through the same `@Autowired` mechanism on container-managed beans. The differences go beyond syntax:
- Field injection assigns the field directly after construction.
- Setter injection invokes a configuration method for a single dependency (typically).
- Multi-argument method injection resolves multiple dependencies before calling an arbitrarily named method.
- A non-required method is allowed to skip **the entire invocation** when a required dependency is missing, whereas `Optional<T>` lets the method run with the optional parameter in an empty state.
- Choose the mechanism based on the object's contract and testability, not just line count.

References:
- [Spring Framework – Using @Autowired](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [Spring Framework – Annotation-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config.html)
- [Spring Framework – Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Spring Framework – Fine-tuning Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)
- [Spring API – AutowiredAnnotationBeanPostProcessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/annotation/AutowiredAnnotationBeanPostProcessor.html)
- [Spring – Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Java 17 – Optional API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html)

**Takeaway:** Annotations do not replace bean registration. Always ask **whether the object is managed by Spring**, **which parameters the injection point requires**, **whether a missing parameter fails or skips the method**, and **whether the dependency is truly optional**. Answering these four questions lets you use field/setter/multi-parameter injection intentionally and debug effectively when configuration changes.