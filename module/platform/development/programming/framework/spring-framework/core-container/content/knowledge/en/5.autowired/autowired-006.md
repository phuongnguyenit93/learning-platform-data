# Distinguishing `@Autowired` from `jakarta.inject.Inject` — Spring Framework Core Container

## 1. Two Annotations Both Solving Dependency Injection, From Different Origins

In the Spring Core Container, **`@Autowired`** is Spring's own annotation, whereas **`@Inject`** is Jakarta's standard Dependency Injection annotation, located in package **`jakarta.inject`**. Spring Framework 6.2 can recognize **both** when instantiating beans, provided the Jakarta Inject API library is present on the classpath.

The following two constructors express the same basic intent — **Spring supplies the `MessageSender` bean to the service**:

~~~java
// Spring style:
@Autowired
public SpringClient(MessageSender sender) {
    this.sender = sender;
}

// Jakarta standard style:
@Inject
public StandardClient(MessageSender sender) {
    this.sender = sender;
}
~~~

These are **two snippets from two different classes**, without full classes/imports; a runnable project is in section 7. In both cases, the container must find the right `MessageSender` candidate and pass the **bean object** into the constructor. An annotation does not automatically create a bean if the class has not been registered with the context.

**Lesson objective:** understand the similarities, differences, limitations of the Jakarta standard, and how to choose annotations sensibly when writing Java 17+ with Spring Framework.

After this article, you will be able to:

1. Distinguish importing `org.springframework.beans.factory.annotation.Autowired` from `jakarta.inject.Inject`.
2. Use both annotations on **constructor, field, or method injection** within a Spring context.
3. Understand that `@Autowired(required=false)` **has no identical attribute counterpart** on `@Inject`; know how to use `Optional<T>`, nullable types, or providers when a dependency is truly optional.
4. Distinguish Spring's `@Qualifier("...")` from Jakarta's `@Named("...")`; understand that `jakarta.inject.Qualifier` is a **meta-annotation**.
5. Use `jakarta.inject.Provider<T>` for **retrieving dependencies on demand**, while understanding it does not automatically make a missing dependency valid.
6. Know that `@Named` can serve as a component registration marker, yet **does not create a bean without registration/scanning**.
7. Understand why Spring-specific `@Value`, `@Lazy`, scopes, and other configuration features still play a role even when using `@Inject`.
8. Run a standalone **Java 17+** example with Maven, `javac`/`java`, and verify the stdout lines.

**Scope:** comparing **`@Autowired` and `jakarta.inject.Inject` in the Spring Framework Core Container**. No Spring Boot, MVC, Servlet, JPA, or another CDI container required.

## 2. Exact Comparison Table

| Criterion | Spring `@Autowired` | Jakarta `@Inject` |
| --- | --- | --- |
| Package/import | `org.springframework.beans.factory.annotation.Autowired` | `jakarta.inject.Inject` |
| Ecosystem | Spring Framework | Jakarta Dependency Injection (JSR-330 lineage) |
| Constructor injection | Yes | Yes |
| Field injection | Yes | Yes |
| Method/setter injection | Yes | Yes |
| Marking required dependencies | `required=true` by default | No `required` attribute; normal injection is required |
| Optional injection | `required=false` at supported injection points; also supports `Optional` | No `required=false`; Spring supports `Optional<T>`, `@Nullable` at suitable injection points |
| Selecting a bean by name/qualifier | `@Qualifier("mainSender")` | `@Named("mainSender")` |
| Retrieving beans on demand | Spring `ObjectProvider<T>`/`ObjectFactory<T>` | Jakarta `Provider<T>` with `get()` |
| Component registration via stereotype | `@Component` | `@Named` |
| Declaring configuration values | Uses Spring's `@Value` / `Environment` | No `@Value` equivalent in Jakarta Inject |
| Deferring bean initialization | Uses Spring's `@Lazy` when appropriate | No `@Lazy` annotation equivalent in Jakarta Inject |
| Additional Maven dependency | Included in Spring modules | Requires `jakarta.inject:jakarta.inject-api` on compile/runtime classpath |
| Container dependency at runtime | Spring recognizes and executes it | Same Spring container also recognizes and executes it when Jakarta API is present |

**Do not call `@Inject` a "Spring annotation":** its API is a Jakarta standard. However, when running inside **Spring**, Spring itself still provides the lifecycle, candidate resolution, bean scopes, and extension points. Using standard annotations **does not automatically make a Spring application completely independent of Spring**.

## 3. By What Mechanism Does Spring Recognize `@Inject`?

In Spring's annotation-based configuration, `AutowiredAnnotationBeanPostProcessor` participates in detecting injection points and performing wiring. Spring supports its own `@Autowired`/`@Value` annotations, and also supports **`jakarta.inject.Inject` when the corresponding API is present**.

Prerequisites:

1. The target class to inject must **become a Spring bean**, e.g., scanned from an appropriate package or registered directly via `AnnotationConfigApplicationContext.register(...)`.
2. Collaborator beans must be declared via `@Bean`, component scanning, or another valid bean definition registration method.
3. The container must be able to resolve injection points by **type**, **qualifiers**, **scope**, and Spring rules.
4. For `@Inject`, Maven must include **Jakarta Inject API**; missing the library causes a compile error or classpath issue, not an intrinsic DI error.

~~~mermaid
flowchart TD
    A["Class already registered as a Spring bean"] --> B["Spring processes injection annotations"]
    B --> C["Spring's @Autowired"]
    B --> D["Jakarta's @Inject"]
    C --> E["Find matching bean candidate"]
    D --> E
    E --> F["Constructor / field / setter receives object"]
    F --> G["Bean uses collaborator"]
~~~

**Distinguish two phases:** `@Named`/`@Component` can serve as a stereotype helping Spring **discover the class** during component scanning, whereas `@Inject`/`@Autowired` marks **points needing wiring**. They serve different roles.

### `@Named` Differs from `@Inject`

- `@Named("standardClient")` on a class can assign the component name in Spring.
- `@Named("mainSender")` on a **constructor parameter** can act as a qualifier to select a specific bean.
- `@Inject` on a constructor expresses the request for the container **to supply the parameters**.
- A class carrying `@Named` that **lies outside the scan scope and is not directly registered** will not automatically appear in the context.

## 4. Constructor Injection: Both Annotations Usually Work Equivalently

In a context with a single `MessageSender` bean, both approaches below are handled by Spring:

~~~java
@Component
final class SpringConsumer {
    private final MessageSender sender;

    @Autowired
    SpringConsumer(MessageSender sender) {
        this.sender = java.util.Objects.requireNonNull(sender);
    }
}
~~~

~~~java
@Named
final class JakartaConsumer {
    private final MessageSender sender;

    @Inject
    JakartaConsumer(MessageSender sender) {
        this.sender = java.util.Objects.requireNonNull(sender);
    }
}
~~~

Both are **illustrative snippets** without an accompanying `MessageSender` definition. When registered with Spring and having a valid collaborator, the constructor receives the bean. Keeping the collaborator in `private final` and checking non-null are **Java code** designs, not an exclusive feature of either annotation.

### A Single Constructor May Need Neither

With modern Spring Framework, if a class is registered as a bean and **has only one constructor**, Spring can use that constructor **even without writing `@Autowired` or `@Inject`**:

~~~java
@Component
final class PlainConsumer {
    private final MessageSender sender;

    PlainConsumer(MessageSender sender) {
        this.sender = java.util.Objects.requireNonNull(sender);
    }
}
~~~

So do not add `@Inject` just thinking **every Spring bean constructor must have an annotation**. Annotations are useful to clarify the injection point, especially when a class has multiple constructors. If the class is created **via `new` inside a `@Bean` factory method**, Java decides the specific overload via that `new` call; it does not automatically mean Spring re-selects a constructor on the returned object.

### If the Class Has Multiple Constructors

- `@Autowired` allows describing a required constructor (default) or multiple `required=false` candidates per Spring rules.
- `@Inject` **has no `required` parameter**. Do not apply `@Inject(required=false)` syntax — Java will fail to compile.
- With multiple overloads, prefer **one clear required constructor**; do not rely on the container guessing business intent.
- Avoid putting `@Inject` on multiple constructors expecting Spring to treat them as a `required=false` list. A class with multiple constructors needs an explicit choice.
- Do not use a default constructor that produces a missing-dependency state just so the app starts up.

**Important:** `@Autowired(required=false)` on a **setter method** and on a **constructor** have different semantics: on a setter, the method can be skipped when the dependency is absent; with multiple optional annotated constructors, Spring selects a satisfiable constructor per rules. Do not interpret `required=false` as passing null to every missing parameter.

## 5. Major Difference: Handling Optional Dependencies

### 5.1. Spring: `@Autowired(required=false)` on a Setter

~~~java
@Component
final class OptionalMonitoring {
    private boolean metricsAttached;

    @Autowired(required = false)
    public void setMetrics(MetricsClient metrics) {
        metricsAttached = true;
    }

    boolean metricsAttached() {
        return metricsAttached;
    }
}
~~~

This is a **snippet**; `MetricsClient` is not defined in this standalone excerpt. If Spring has no matching `MetricsClient` bean, it can **skip calling the optional setter**; `metricsAttached` remains `false`. The runnable example in section 7 verifies this.

### 5.2. Jakarta: No `required=false`; Use `Optional<T>` When Appropriate

~~~java
@Named
final class OptionalJakartaClient {
    private final java.util.Optional<MetricsClient> metrics;

    @Inject
    OptionalJakartaClient(java.util.Optional<MetricsClient> metrics) {
        this.metrics = java.util.Objects.requireNonNull(metrics);
    }

    boolean missing() {
        return metrics.isEmpty();
    }
}
~~~

**Snippet**, requires declaring `MetricsClient`. In **Spring**, when no matching `MetricsClient` bean exists, an injection point of type `Optional<MetricsClient>` can receive `Optional.empty()`. This is supported by Spring documentation for `@Inject`.

| Intent | How to Express |
| --- | --- |
| **Required** dependency | Standard constructor injection, with `@Autowired` or `@Inject` |
| Spring optional setter | `@Autowired(required=false)` on the appropriate setter |
| Optional parameter in Spring | `Optional<T>` or nullable injection point with matching rules |
| On-demand dependency access | `jakarta.inject.Provider<T>` or Spring `ObjectProvider<T>` |

**Do not confuse `Provider` with `Optional`.** `Provider<T>.get()` **demands an instance**; if the bean does not exist, calling `get()` can fail. Provider defers/dynamically handles access, **not a guarantee of "if bean missing, always return null"**.

### 5.3. Optional Differs from "Running When Missing Is Okay"

If a payment-processing service **cannot function without `PaymentGateway`**, marking the dependency optional just to avoid a startup error is a design bug. Keep the constructor required and let the context **fail fast** when the bean is missing.

Use optionality for genuinely non-essential components, such as metrics, auxiliary tracing, plugins, or toggleable features. When absent, code must define intentional behavior; do not merely ignore `NullPointerException`.

## 6. `@Qualifier`, `@Named`, `Provider`, and `@Value`

### 6.1. Selecting a Bean by Name

If multiple beans share type `MessageSender`, the injection point must specify the desired one.

**Spring:**

~~~java
@Autowired
public SpringClient(
        @Qualifier("mainSender") MessageSender sender) {
    this.sender = sender;
}
~~~

**Jakarta:**

~~~java
@Inject
public StandardClient(
        @Named("mainSender") MessageSender sender) {
    this.sender = sender;
}
~~~

These are **snippets from two classes**, not standalone files. In a Spring context, both direct Spring to the bean with the matching name/qualifier. `@Named` is also used on a class to mark a component name.

**Note:** `jakarta.inject.Qualifier` is a **meta-annotation** for building custom qualifiers, not an annotation taking a name parameter like Spring's `@Qualifier("mainSender")`. To use a String name in Jakarta, use `@Named("mainSender")`.

### 6.2. `Provider<T>` Retrieves a Bean When Needed

~~~java
@Named
final class LazyConsumer {
    private final Provider<MessageSender> senderProvider;

    @Inject
    LazyConsumer(Provider<MessageSender> senderProvider) {
        this.senderProvider = senderProvider;
    }

    String run() {
        return senderProvider.get().send("Lan");
    }
}
~~~

**Illustrative snippet:** requires importing `jakarta.inject.Provider` and a `MessageSender` type with a `send` method. Spring supports `Provider<T>` when Jakarta Inject API is present. With a standard singleton, multiple `get()` calls return the same instance; with a prototype, each lookup can create a new instance. Do not claim `Provider` automatically turns a bean into prototype scope or never triggers bean creation logic.

### 6.3. No Direct `@Value` or `@Lazy` Equivalent in Jakarta Inject

Jakarta `@Inject` focuses on injecting **bean objects**. It does not provide annotations equivalent to Spring's `@Value` for resolving property placeholders directly, or Spring's `@Lazy` for declaring lazy initialization. When using Spring, you can combine Jakarta annotations with Spring features:

~~~java
@Inject
public ConfigurableClient(
        @Named("mainSender") MessageSender sender,
        @Value("${app.prefix}") String prefix) {
    this.sender = sender;
    this.prefix = prefix;
}
~~~

This is a **snippet**, requiring Spring's `@Value` class/import and appropriate property source configuration; not a runnable file. It shows that **mixing annotations is possible**, though the class now **depends on Spring-specific configuration semantics** and is no longer "Jakarta-only".

For simple values, one can read `Environment.getRequiredProperty(...)` at the composition root and pass them into the constructor; do not turn every String or int into a bean just to use `@Inject`.

### 6.4. Scope and Stereotype

In Spring, a `@Named` class registered as a Spring bean normally still has **default singleton scope**, just like a `@Component` class under Spring defaults. Even though the Jakarta standard has its own interpretation of scope when unspecified, do not assume Spring automatically converts `@Named` to prototype.

If prototype scope is needed in Spring:

~~~java
@Named("temporaryHandler")
@org.springframework.context.annotation.Scope("prototype")
final class TemporaryHandler {
    // A new instance per appropriate request.
}
~~~

Illustrative snippet only. `jakarta.inject.Singleton` is a standard scope annotation, yet in Spring **it does not need to be attached to every bean to get default singleton behavior**.

Do not replace `@ComponentScan`/registration by merely importing `@Named`: the class must still be visible to the scanner or registered directly.

## 7. Standalone Java 17+ Example — Both Annotations in the Same Spring Context

### 7.1. Structure and Dependencies

Uses **Spring Framework 6.2.19**, **JDK 17+**, Maven, and Jakarta Inject API **2.0.0**. Versions are pinned for the example, not claimed as the latest Spring release.

~~~text
spring-jakarta-inject-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── InjectionComparisonDemo.java
~~~

`pom.xml` file:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-jakarta-inject-demo</artifactId>
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
        <dependency>
            <groupId>jakarta.inject</groupId>
            <artifactId>jakarta.inject-api</artifactId>
            <version>2.0.0</version>
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
                    <mainClass>demo.InjectionComparisonDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Both dependencies are required**: `spring-context` brings the Spring container into the program; `jakarta.inject-api` provides `Inject`, `Named`, and `Provider` for compilation and for Spring to recognize them at runtime.

### 7.2. Source Code src/main/java/demo/InjectionComparisonDemo.java

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

import jakarta.inject.Inject;
import jakarta.inject.Named;
import jakarta.inject.Provider;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Component;

public final class InjectionComparisonDemo {
    private InjectionComparisonDemo() {}

    public interface MessageSender {
        String send(String name);
    }

    public static final class ConsoleSender implements MessageSender {
        @Override
        public String send(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name required");
            }
            return "Xin chao, " + name.strip();
        }
    }

    public static final class EventLog {
        private final List<String> events = new ArrayList<>();

        public void record(String event) {
            events.add(event);
        }

        public List<String> snapshot() {
            return List.copyOf(events);
        }
    }

    // Spring-specific constructor injection.
    @Component("springClient")
    public static final class SpringClient {
        private final MessageSender sender;
        private final EventLog log;

        @Autowired
        public SpringClient(
                @Qualifier("mainSender") MessageSender sender,
                EventLog log) {
            this.sender = Objects.requireNonNull(sender);
            this.log = Objects.requireNonNull(log);
        }

        public MessageSender sender() {
            return sender;
        }

        public String greet(String name) {
            String message = sender.send(name);
            log.record("spring:" + message);
            return message;
        }
    }

    // Jakarta standard constructor injection.
    @Named("standardClient")
    public static final class StandardClient {
        private final MessageSender sender;
        private final EventLog log;

        @Inject
        public StandardClient(
                @Named("mainSender") MessageSender sender,
                EventLog log) {
            this.sender = Objects.requireNonNull(sender);
            this.log = Objects.requireNonNull(log);
        }

        public MessageSender sender() {
            return sender;
        }

        public String greet(String name) {
            String message = sender.send(name);
            log.record("inject:" + message);
            return message;
        }
    }

    // Jakarta Provider resolves the target on get().
    @Named("providerClient")
    public static final class ProviderClient {
        private final Provider<MessageSender> provider;

        @Inject
        public ProviderClient(Provider<MessageSender> provider) {
            this.provider = Objects.requireNonNull(provider);
        }

        public boolean providesSame(MessageSender sender) {
            return provider.get() == sender;
        }
    }

    // No bean of this interface is registered in the example.
    public interface MissingMetrics {}

    @Component("optionalSpringClient")
    public static final class OptionalSpringClient {
        private boolean metricsAttached;

        public OptionalSpringClient() {}

        @Autowired(required = false)
        public void setMetrics(MissingMetrics metrics) {
            metricsAttached = true;
        }

        public boolean setterSkipped() {
            return !metricsAttached;
        }
    }

    @Named("optionalStandardClient")
    public static final class OptionalStandardClient {
        private final Optional<MissingMetrics> metrics;

        @Inject
        public OptionalStandardClient(Optional<MissingMetrics> metrics) {
            this.metrics = Objects.requireNonNull(metrics);
        }

        public boolean absent() {
            return metrics.isEmpty();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean("mainSender")
        public MessageSender mainSender() {
            return new ConsoleSender();
        }

        @Bean
        public EventLog eventLog() {
            return new EventLog();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext()) {
            context.register(AppConfig.class, SpringClient.class,
                    StandardClient.class, ProviderClient.class,
                    OptionalSpringClient.class, OptionalStandardClient.class);
            context.refresh();

            SpringClient spring = context.getBean(SpringClient.class);
            StandardClient standard = context.getBean(StandardClient.class);
            ProviderClient provider = context.getBean(ProviderClient.class);
            OptionalSpringClient optionalSpring =
                    context.getBean(OptionalSpringClient.class);
            OptionalStandardClient optionalStandard =
                    context.getBean(OptionalStandardClient.class);
            MessageSender sender = context.getBean(MessageSender.class);
            EventLog log = context.getBean(EventLog.class);

            System.out.println("springGreeting=" + spring.greet(" Lan "));
            System.out.println("injectGreeting=" + standard.greet(" Minh "));
            System.out.println("sameSender=" +
                    (spring.sender() == sender
                     && standard.sender() == sender));
            System.out.println("providerSame=" +
                    provider.providesSame(sender));
            System.out.println("autowiredSetterSkipped=" +
                    optionalSpring.setterSkipped());
            System.out.println("injectOptionalAbsent=" +
                    optionalStandard.absent());
            System.out.println("events=" + log.snapshot());
            System.out.println("standardSingleton=" +
                    (standard == context.getBean(StandardClient.class)));
        }
    }
}
~~~

**Why the example is self-contained:**

- There is exactly one public top-level class matching the filename; collaborator classes/interfaces are declared nested static.
- The `mainSender` bean has type `MessageSender` and is explicitly named; `eventLog` is a default singleton bean.
- `SpringClient` injects with Spring `@Autowired`/`@Qualifier("mainSender")`.
- `StandardClient` injects the same bean using Jakarta `@Inject`/`@Named("mainSender")`.
- `ProviderClient` injects `jakarta.inject.Provider<MessageSender>`; because the context has only one sender singleton, `provider.get()` returns that exact object.
- `OptionalSpringClient` has no `MissingMetrics` bean, so the `@Autowired(required=false)` setter is not called and the boolean value stays `false`.
- `OptionalStandardClient` uses `Optional<MissingMetrics>` via `@Inject`, thus receiving `Optional.empty()` when the dependency is absent in Spring.
- Both consumers share one `EventLog` singleton and record in the order called by `main`. The demo uses no randomness, clocks, or unstable iteration results.
- `context.register(...)` **directly registers** the component classes; no component scanning is needed. Simply placing `@Component`/`@Named` in source without registering/scanning will not make a class a bean.
- `try-with-resources` closes the context after printing finishes. No bean destroy callback emits stdout.

### 7.3. Run Maven and Verify Stdout

From the `spring-jakarta-inject-demo` directory:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

**Exact eight stdout lines printed by the Java program on a successful run:**

~~~text
springGreeting=Xin chao, Lan
injectGreeting=Xin chao, Minh
sameSender=true
providerSame=true
autowiredSetterSkipped=true
injectOptionalAbsent=true
events=[spring:Xin chao, Lan, inject:Xin chao, Minh]
standardSingleton=true
~~~

Version lines and Maven/Spring logging (if they appear) are outside the eight `System.out.println` lines above. The `true`/`false` states are direct consequences of the demo setup, **not a claim that every annotation selects the same instance under all scopes/circumstances**.

### 7.4. Using `javac`/`java` Directly

Because the source imports both Spring and `jakarta.inject.*`, the compiler needs **both dependency groups** on the classpath. Use Maven to generate the classpath file:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

**Linux/macOS (bash/zsh):**

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -cp "$(cat classpath.txt)" \
  -d out src/main/java/demo/InjectionComparisonDemo.java
java -cp "out:$(cat classpath.txt)" demo.InjectionComparisonDemo
~~~

**Windows PowerShell:**

~~~powershell
$deps = (Get-Content -Raw classpath.txt).Trim()
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -cp "$deps" -d out src/main/java/demo/InjectionComparisonDemo.java
java -cp "out;$deps" demo.InjectionComparisonDemo
~~~

On Unix, classpath entries are separated by `:`, on Windows by `;`. Running the same `demo.InjectionComparisonDemo` class produces business output matching the eight lines above.

If `javac` reports `package jakarta.inject does not exist`, check the `jakarta.inject-api` dependency in the POM/classpath; if `org.springframework...` is missing, check `spring-context` and transitive JARs.

## 8. Explaining the Eight Stdout Lines

| Line | Conclusion Permitted |
| --- | --- |
| `springGreeting=Xin chao, Lan` | `SpringClient` received `sender` and processed the stripped name |
| `injectGreeting=Xin chao, Minh` | `StandardClient` was injected by Spring via `@Inject` |
| `sameSender=true` | Both consumers hold **the same `mainSender` singleton bean** in this context |
| `providerSame=true` | `Provider<MessageSender>.get()` in this context returns the same sender singleton |
| `autowiredSetterSkipped=true` | Spring's optional setter was skipped when the `MissingMetrics` bean was absent |
| `injectOptionalAbsent=true` | `Optional<MissingMetrics>` was resolved as absent |
| `events=[spring:..., inject:...]` | Both services recorded into `EventLog` in order |
| `standardSingleton=true` | The Spring-managed `@Named` bean is singleton by default in the example |

Do not use `sameSender=true` to deduce that **prototypes, scoped proxies, multiple beans of the same type, or multiple contexts** all return the same object. Scope and bean resolution still govern identity.

## 9. Some Common Misconceptions

### 9.1. "`@Inject` automatically replaces every `@Autowired` feature"

No. Spring understands `@Inject` as a basic replacement injection annotation, yet the Jakarta annotation **has no `required` attribute**. Spring `@Autowired` along with facilities such as `@Value`, `@Lazy`, and `ObjectProvider` still offer distinct capabilities. When switching annotations, check optional semantics, providers, qualifiers, and build dependencies.

### 9.2. "Using `@Inject` lets you run on any DI container without changing anything"

The annotation API is standardized and helps decouple **injection code**, yet registration models, bean scopes, lifecycles, external config resolution, custom qualifiers, and container extensions can differ. How Spring supports `Optional<T>` does not mean every other CDI/container behaves identically.

Portability is a **degree**, not a guarantee of migrating an entire Spring app to another container simply by swapping an import.

### 9.3. "Jakarta's `@Named` and `@Qualifier` are the same"

No. `jakarta.inject.Named` is a String-based qualifier that can also be used on component classes. `jakarta.inject.Qualifier` is used as a **meta-annotation** to define custom qualifiers; do not write `@jakarta.inject.Qualifier("mainSender")`. Spring's `@Qualifier("mainSender")` is Spring's own annotation and accepts a value.

### 9.4. "`@Named` turns every class in the project into a bean"

No. With component scanning, the right package must be specified; with programmatic context setup, you can register the class directly. The annotation neither activates a scanner nor writes itself into a registry.

### 9.5. "`Provider<T>` always allows a missing dependency"

No. `Provider` mainly supports **retrieving a dependency at the moment needed**, and also suits prototype/scoped beans. If no valid bean exists, `get()` can throw an exception. If the dependency is truly optional, use `Optional<T>` or an explicit policy at the application layer.

### 9.6. "`@Autowired(required=false)` guarantees a field has value null"

With an optional setter, Spring may **skip the entire method injection** when no collaborator is resolved. A field can remain null/default if uninjected; code must handle that absence behavior. Do not think `required=false` is an instruction to always pass null into a setter.

### 9.7. "`@Inject` means `@Singleton`"

`@Inject` only marks an injection point. A bean's scope is determined by the container/definition. In Spring, `@Named` beans usually default to singleton, not because the constructor has `@Inject`, nor are they prototype by default.

### 9.8. "Use `javax.inject.Inject` because old Java projects did that"

Spring Framework 6+ uses the Jakarta APIs in standard documentation. In new Java 17+ projects, prefer `jakarta.inject.Inject`/`Named` and the `jakarta.inject-api` dependency. `javax.inject.Inject` belongs to the legacy Java EE/JSR-330 namespace; Spring may retain compatibility support in some versions/contexts, but **do not mix the two namespaces** without understanding exact dependencies and migration environments.

### 9.9. "Having `@Inject` means no null checks are needed"

Dependency injection does not replace Java invariants:

~~~java
@Inject
public BillingService(PaymentGateway gateway) {
    this.gateway = java.util.Objects.requireNonNull(gateway);
}
~~~

This snippet lacks full `BillingService`/`PaymentGateway` definitions. Guards remain helpful when the class is created **outside Spring** via `new` or when callers/adapters pass invalid data. Do not turn a required dependency into nullable merely to bypass wiring errors.

## 10. Common Errors and Troubleshooting

| Symptom | Possible Cause | How to Fix |
| --- | --- | --- |
| `package jakarta.inject does not exist` | Jakarta Inject API library not declared | Add Maven dependency, update build/classpath |
| `cannot find symbol @Inject` | Wrong import or missing dependency | Import `jakarta.inject.Inject` |
| `@Inject(required=false)` fails to compile | Jakarta `@Inject` has no `required` attribute | Use `Optional<T>`/nullable/provider per contract |
| `UnsatisfiedDependencyException` | Required bean constructor missing collaborator | Register bean, check scan/qualifiers |
| `NoSuchBeanDefinitionException` | No bean matching desired type/name | Check `@Bean`, `@Named`, context configuration |
| `NoUniqueBeanDefinitionException` | Multiple bean candidates for a single-valued parameter | Select via `@Qualifier`/`@Named` or primary policy |
| `@Autowired(required=false)` setter does not run | Optional bean does not exist | That may be the intended semantics; verify optional contract |
| `Provider.get()` fails | No suitable bean available at retrieval time | Check availability/scope, do not treat `Provider` as `Optional` |
| `@Named` class not discovered | Missing component scan or explicit registration | Configure scan scope or register the class directly |
| Using `@Named` to read property placeholders | Confusing bean selector with value configuration | Use `@Value`/`Environment` appropriately |
| `@Inject` present yet property remains null | Object `new`'d outside container or bean processing inactive | Use a managed bean, check registration/post-processing |
| Scope differences across environments | Applying another container's semantics to Spring | Check the bean definition's scope in Spring |
| Randomly swapping `javax.inject`/`jakarta.inject` imports | Different namespaces, mismatched dependencies | Standardize on Jakarta namespace for Spring 6+ and check migrations |
| Spring test passes yet business logic is wrong | Successful wiring does not prove correct business behavior | Write unit tests with fakes and integration tests |

**How to debug:** identify the bean source/registration, which package the annotation is imported from, what type the injection point expects, how many candidates exist, whether the qualifier is accurate, whether the dependency is optional or required, and then read the exception's `Caused by` chain. If there is a compile error, fix dependencies **before** analyzing Spring runtime behavior.

## 11. Extended Practice

**Exercise 1 — missing required bean:** create a `@Named` class with constructor `@Inject RequiredClient(MissingMetrics metrics)` and register it in a **separate test context** without registering `MissingMetrics`. Expect refresh to fail; do not expect Spring to pass null or skip the constructor.

**Exercise 2 — changing qualifiers:** register a second sender named `backupSender`. Keep `@Qualifier("mainSender")` and `@Named("mainSender")` injections: both consumers still request the primary sender. Remove the qualifiers and explain the ambiguity cause when multiple candidates have no other disambiguator.

**Exercise 3 — singleton vs prototype:** change a valid bean to `@Scope("prototype")`, then call `Provider<T>.get()` twice; check object identity per actual scope. Do not edit the original demo code and still expect stdout `providerSame=true`.

**Exercise 4 — Optional:** register a `MissingMetrics` bean in another test, verify `Optional<MissingMetrics>.isPresent()` becomes true and the optional setter gets called. Remember to test the absent case as well.

**Exercise 5 — plain Java:** construct `SpringClient` or `StandardClient` via constructor with a fake sender and fake log. Both are testable as ordinary Java classes; starting Spring is not required just to test greeting logic.

### Lesson Wrap-Up Checklist

- [ ] Know the different imports and dependencies of `@Autowired` and `@Inject`.
- [ ] Both can perform constructor/field/setter injection in Spring.
- [ ] Do not assume annotations automatically register a class as a bean.
- [ ] Use one clear constructor for required collaborators.
- [ ] Know `@Autowired` has `required`, whereas `@Inject` does not.
- [ ] Choose appropriate `Optional`/nullable semantics for genuinely optional dependencies.
- [ ] Distinguish `Provider` retrieving beans on demand from `Optional` expressing absence.
- [ ] Use Spring's `@Qualifier("name")` or Jakarta's `@Named("name")` in their proper roles.
- [ ] Know `jakarta.inject.Qualifier` is a meta-annotation.
- [ ] Do not assume `@Named` defaults to prototype scope in Spring.
- [ ] Understand `@Value`/`@Lazy` are Spring features without direct Jakarta annotation equivalents.
- [ ] Include `jakarta.inject-api` in the POM and compile/runtime classpath.
- [ ] Run `mvn -q clean compile exec:java` and verify the **eight stdout lines**.
- [ ] With `javac`/`java`, supply both Spring + Jakarta JARs.
- [ ] Test behavior at the unit level and wiring at the context level.

**Conclusion:** in Spring, both `@Autowired` and `jakarta.inject.Inject` can declare dependency injection. Choose `@Inject` if you want the **standard Jakarta annotation API** for basic DI needs, and `@Autowired` if you need to directly express Spring-specific capabilities like `required=false` on an injection point. Either way, **registration, bean selection, scope, and lifecycle remain governed by the Spring container** when running on Spring Framework.

### Official Documentation

- [Spring Framework 6.2 — Using JSR-330 Standard Annotations](https://docs.spring.io/spring-framework/reference/6.2/core/beans/standard-annotations.html)
- [Spring Framework 6.2 — Using @Autowired](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [Spring Framework 6.2 — Annotation-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config.html)
- [Spring API — AutowiredAnnotationBeanPostProcessor](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/annotation/AutowiredAnnotationBeanPostProcessor.html)
