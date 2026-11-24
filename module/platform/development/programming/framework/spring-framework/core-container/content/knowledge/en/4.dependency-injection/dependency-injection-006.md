# Distinguishing Bean References from Simple Values — Spring Framework Core Container

## 1. Goal: Pinpoint Exactly What Is Being Injected

In the Spring IoC container, a constructor or factory method can take multiple parameters: some parameters are **collaborator beans** registered and managed by Spring; others are simply **configuration values** such as strings, numbers, booleans, or timeouts. Both are passed into a Java method, yet **their meaning and resolution mechanisms differ**.

For example, `GreetingService` needs:

- `NameFormatter`: a shared **bean object** to normalize names.
- `prefix`: the string `"Xin chao"` from configuration.
- `maxChars`: the integer `8` from configuration, used to cap name length.

`NameFormatter` is a **bean dependency**. `prefix` and `maxChars` are **values**; they do not automatically become Spring beans just because they appear in the constructor.

After this lesson you can:

1. Distinguish bean reference, bean name, literal value, external configuration value, and bean instance.
2. Identify which constructor/factory-method arguments Spring should resolve as beans and which must be supplied from configuration or Java data.
3. Use `@Bean` factory methods and `Environment.getRequiredProperty(...)` to pass both the right collaborators and `String`/`Integer` values.
4. Explain how `@Value`/property placeholders differ from `@Qualifier`/bean lookup.
5. Distinguish `BeanDefinitionBuilder.addPropertyValue(...)` from `addPropertyReference(...)` and how `RuntimeBeanReference` is resolved into an object.
6. Verify metadata and wiring on a plain Spring Framework example runnable with Java 17+.
7. Handle missing beans, multiple beans of the same type, missing properties, wrong types, wrong setters, scopes, and common misconceptions.

**Scope:** *distinguishing bean references from simple/configuration values in dependency injection*. Spring Boot, Spring MVC, JPA, and frameworks outside Core Container are not needed.

## 2. Concepts at the Right Abstraction Layer

| Concept | Example | How the Container Interprets It |
| --- | --- | --- |
| Java type | `NameFormatter`, `String`, `int` | Parameter/field type; does not by itself declare bean vs. value |
| Bean name | `"nameFormatter"` | Identifier key for a bean in the registry |
| Bean reference | Bean object supplied to `NameFormatter formatter` | A dependency on a container-managed object |
| Literal value | `"manual"`, `8` | Direct data passed into a constructor/setter |
| External configuration value | Property `greeting.prefix=Xin chao` | Read from `Environment` or a value-resolution mechanism |
| `RuntimeBeanReference` | Metadata pointing to a bean named `nameFormatter` | Not an object yet; Spring resolves it when creating the bean |
| Bean instance | Actual `UppercaseFormatter` object | Instantiated object, potentially shared per scope |

**Having a name is not yet a reference.** These two lines are not equivalent:

~~~java
.addPropertyValue("formatter", "nameFormatter")
.addPropertyReference("formatter", "nameFormatter")
~~~

These are **configuration snippets**, not standalone Java statements. The first line passes a `String` literal containing the text `nameFormatter` to the property; the second tells Spring to **find the bean named `nameFormatter` and inject that object** into the `formatter` property. If the setter takes a `NameFormatter`, the second line is normally required.

### One Diagram with Two Distinct Inputs

~~~mermaid
flowchart LR
    E1["Environment: greeting.prefix"] -->|"String value"| S["greetingService: GreetingService"]
    E2["Environment: greeting.maxChars"] -->|"int value"| S
    B["nameFormatter: NameFormatter"] -->|"bean object"| S
    L["literal: manual"] -->|"String value"| M["manualGreeting: ManualGreeting"]
    B -->|"bean reference"| M
~~~

The diagram uses arrow direction to show **values/objects supplied to the consumer**. If drawing a dependency graph in the **consumer → dependency** direction, the bean edges are `greetingService → nameFormatter` and `manualGreeting → nameFormatter`. String/int values do not necessarily appear as separate bean nodes.

## 3. A Java Constructor Taking Beans and Values Is Still a Normal Constructor

Spring-free Java design:

~~~java
public final class GreetingService {
    private final NameFormatter formatter; // collaborator
    private final String prefix;            // configuration value
    private final int maxChars;              // configuration value

    public GreetingService(
            NameFormatter formatter, String prefix, int maxChars) {
        this.formatter =
                java.util.Objects.requireNonNull(formatter);
        if (prefix == null || prefix.isBlank()) {
            throw new IllegalArgumentException("prefix required");
        }
        if (maxChars <= 0) {
            throw new IllegalArgumentException("maxChars must be positive");
        }
        this.prefix = prefix;
        this.maxChars = maxChars;
    }
}
~~~

**Illustrative snippet**, missing `NameFormatter` and a valid enclosing public class. It shows:

- `formatter` is a **collaborator object**. Spring must check whether a bean satisfies type `NameFormatter`.
- `prefix` is **String data**, which must come from configuration or the caller, not implicitly from a bean of that name.
- `maxChars` is an **integer**, which must be read/converted and validated.
- The constructor enforces invariants: non-null collaborator, non-blank prefix, positive maxChars. Spring does not replace domain validation defined by the Java class itself.
- `final` fields keep references/values from being reassigned; **they do not imply deep immutability** or thread safety of a mutable collaborator.

Plain Java can instantiate the object when all arguments are provided:

~~~java
NameFormatter formatter = new UppercaseFormatter();
GreetingService service =
        new GreetingService(formatter, "Hello", 12);
~~~

This is **manual dependency injection**, without Spring yet. The container only automates selecting/creating beans and supplying values according to the configuration you define.

### Do Not Label Every Parameter as a Bean

Spring should not be asked to “autowire by type” a `String` or an `int` merely because a service constructor accepts them. Under default autowiring, simple properties such as primitives, `String`, and `Class` are not automatically autowired like regular collaborators in the same way. To give values clear meaning, use `Environment`, `@Value`, literal values at the composition root, or an explicitly declared configuration object.

You can deliberately register a bean of type `String`, yet that is a specific configuration choice—**do not turn every String in the application into a bean**. Avoid creating dozens of anonymous `@Bean String` definitions that blur data and services.

## 4. How JavaConfig Passes Both Input Kinds at the Right Boundary

An example configuration class:

~~~java
@Configuration(proxyBeanMethods = false)
class AppConfig {
    @Bean
    NameFormatter nameFormatter() {
        return new UppercaseFormatter();
    }

    @Bean
    GreetingService greetingService(
            NameFormatter formatter, Environment env) {
        String prefix =
                env.getRequiredProperty("greeting.prefix");
        int maxChars =
                env.getRequiredProperty("greeting.maxChars", Integer.class);
        return new GreetingService(formatter, prefix, maxChars);
    }
}
~~~

**This is an illustrative snippet**; the full example is in section 6. How to read it:

1. `@Bean nameFormatter()` creates and registers a managed `NameFormatter` bean.
2. `@Bean greetingService(NameFormatter formatter, Environment env)` takes one collaborator by type and an `Environment` parameter supplied by Spring.
3. Spring resolves the `NameFormatter` bean and passes that exact object into the service factory method.
4. The factory method reads two configuration keys; `prefix` is a String, while `maxChars` is converted to `Integer` and unboxed to `int`.
5. The factory method constructs the service with both **bean reference + simple values**. If a required key is missing or unconvertible, bean creation fails rather than silently substituting null or zero.
6. `@Configuration(proxyBeanMethods=false)` is valid because factory methods **do not call each other directly**; Spring performs wiring through method parameters.

**Do not conclude that “`Environment` is a simple value”.** `Environment` is a Spring abstraction passed into the factory method; the properties read *from it* are the simple values in the example. It is not the same as a `String` randomly looked up as a bean by type.

### `@Value` as Another Way to Supply Simple Values

You can use:

~~~java
@Bean
GreetingService greetingService(
        NameFormatter formatter,
        @Value("${greeting.prefix}") String prefix,
        @Value("${greeting.maxChars}") int maxChars) {
    return new GreetingService(formatter, prefix, maxChars);
}
~~~

**Alternative snippet**, requiring importing `org.springframework.beans.factory.annotation.Value`, property sources, and appropriate placeholder resolution. Here `@Value("${greeting.prefix}")` intends to resolve a **value** from configuration; `NameFormatter formatter` remains a **bean dependency**. `@Value` can also evaluate Spring Expression Language expressions depending on configuration, though that is unnecessary in this lesson.

Comparison:

| Syntax | Meaning |
| --- | --- |
| `@Value("${greeting.prefix}") String prefix` | Resolve configuration into a String for the parameter |
| `@Value("${greeting.maxChars}") int maxChars` | Resolve and convert the value into the matching int |
| `@Qualifier("nameFormatter") NameFormatter formatter` | Select a **bean candidate**, not read a String property |
| `environment.getRequiredProperty("greeting.prefix")` | Explicitly read property; fail if the required key is missing |
| `@Bean NameFormatter nameFormatter()` | Register how to create a **bean object** rather than a String value |

Caveat: placeholder expressions `${key}` require compatible property sources and resolution setup. Do not assume a missing key is always handled identically to `Environment.getRequiredProperty(...)` in every context type. The runnable example uses `Environment` so the **required-key** rule is completely transparent.

## 5. `BeanDefinition`: How Do Values and References Live in Metadata?

Spring can store object configuration not only via `@Bean` factory methods, but also as **`BeanDefinition` metadata**:

~~~java
BeanDefinition definition = BeanDefinitionBuilder
        .genericBeanDefinition(ManualGreeting.class)
        .addPropertyValue("label", "manual")
        .addPropertyReference("formatter", "nameFormatter")
        .getBeanDefinition();

context.registerBeanDefinition("manualGreeting", definition);
~~~

This is a **snippet**; it needs the matching classes and context from section 6. The two calls do different things:

- `addPropertyValue("label", "manual")` stores a literal value. When `manualGreeting` is instantiated, Spring finds property `label` and invokes setter `setLabel(String)` with the String `"manual"`.
- `addPropertyReference("formatter", "nameFormatter")` stores a **`RuntimeBeanReference`** (or equivalent resolution metadata) pointing to a bean name. At bean creation, Spring resolves the `nameFormatter` object, then calls `setFormatter(NameFormatter)`.

The setter must match in **name, writability, and target type**. If `ManualGreeting` lacks `setFormatter(NameFormatter)` or the bean name does not exist, Spring cannot construct a valid bean.

### Metadata Holds the Name; Runtime Holds the Object

You can inspect it:

~~~java
BeanDefinition stored = context.getBeanFactory()
        .getBeanDefinition("manualGreeting");
PropertyValue labelProperty =
        stored.getPropertyValues().getPropertyValue("label");
PropertyValue formatterProperty =
        stored.getPropertyValues().getPropertyValue("formatter");
RuntimeBeanReference ref =
        (RuntimeBeanReference) formatterProperty.getValue();

System.out.println(labelProperty.getValue()); // manual
System.out.println(ref.getBeanName());          // nameFormatter
~~~

**Snippet excerpted from the full example**, needing imports for `PropertyValue` and `RuntimeBeanReference`. Here:

- `ref.getBeanName()` returns the String **name of the referenced bean**.
- Once Spring initializes `ManualGreeting`, `manual.formatter()` is the **`NameFormatter` object**.
- Inspecting the bean definition alone does not prove the setter has run; use identity/behavior tests to verify the runtime instance.
- `RuntimeBeanReference` is neither a service nor a proxy for calling business methods; it is metadata for the container.

### What Happens If Value Is Used in the Wrong Place?

~~~java
.addPropertyValue("formatter", "nameFormatter")
~~~

This is **semantically wrong in the example**: the author is passing a String literal to a setter expecting `NameFormatter`. Spring does not automatically treat every String that looks like a bean name as a command to look up a managed bean. If you want the **object**, express the reference explicitly; if you want the **name** for display/logging, the property should have type `String` and use a value.

Do not rely on a mysterious custom converter to paper over this design mistake.

## 6. Runnable Spring Framework + Java 17+ Project

Uses **Spring Framework 6.2.19**, JDK 17+, and Maven. The version is pinned so the example is reproducible; this does not imply it is the newest Spring release. No Spring Boot, HTTP server, or database required.

Project:

~~~text
bean-reference-vs-value/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── BeanReferenceVsValueDemo.java
~~~

### 6.1. `pom.xml` File

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bean-reference-vs-value</artifactId>
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
                    <mainClass>demo.BeanReferenceVsValueDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Maven pulls in the required Spring dependencies; `spring-context` is not the only JAR present on the runtime classpath. If using `javac` directly, you need the Spring API JARs and transitive dependencies resolved by Maven.

### 6.2. `src/main/java/demo/BeanReferenceVsValueDemo.java` File

~~~java
package demo;

import java.util.Locale;
import java.util.Map;
import java.util.Objects;

import org.springframework.beans.PropertyValue;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.beans.factory.config.RuntimeBeanReference;
import org.springframework.beans.factory.support.BeanDefinitionBuilder;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;

public final class BeanReferenceVsValueDemo {
    private BeanReferenceVsValueDemo() {}

    public interface NameFormatter {
        String normalize(String raw);
    }

    public static final class UppercaseFormatter implements NameFormatter {
        @Override
        public String normalize(String raw) {
            if (raw == null || raw.isBlank()) {
                throw new IllegalArgumentException("name must not be blank");
            }
            return raw.strip().toUpperCase(Locale.ROOT);
        }
    }

    public static final class GreetingService {
        private final NameFormatter formatter;
        private final String prefix;
        private final int maxChars;

        public GreetingService(
                NameFormatter formatter, String prefix, int maxChars) {
            this.formatter = Objects.requireNonNull(formatter);
            if (prefix == null || prefix.isBlank()) {
                throw new IllegalArgumentException("prefix required");
            }
            if (maxChars <= 0) {
                throw new IllegalArgumentException("maxChars must be positive");
            }
            this.prefix = prefix;
            this.maxChars = maxChars;
        }

        public NameFormatter formatter() {
            return formatter;
        }

        public String greet(String name) {
            String normalized = formatter.normalize(name);
            if (normalized.length() > maxChars) {
                throw new IllegalArgumentException("name too long");
            }
            return prefix + ", " + normalized + "!";
        }
    }

    public static final class ManualGreeting {
        private String label;
        private NameFormatter formatter;

        public ManualGreeting() {}

        public void setLabel(String label) {
            this.label = Objects.requireNonNull(label);
        }

        public void setFormatter(NameFormatter formatter) {
            this.formatter = Objects.requireNonNull(formatter);
        }

        public NameFormatter formatter() {
            return formatter;
        }

        public String greet(String rawName) {
            return label + ":" + formatter.normalize(rawName);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public NameFormatter nameFormatter() {
            return new UppercaseFormatter();
        }

        @Bean
        public GreetingService greetingService(
                NameFormatter formatter, Environment env) {
            String prefix =
                    env.getRequiredProperty("greeting.prefix");
            int maxChars =
                    env.getRequiredProperty("greeting.maxChars", Integer.class);
            return new GreetingService(formatter, prefix, maxChars);
        }
    }

    public static void main(String[] args) {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();

        try (context) {
            context.getEnvironment().getPropertySources().addFirst(
                    new MapPropertySource("lessonProperties",
                            Map.<String, Object>of(
                                    "greeting.prefix", "Xin chao",
                                    "greeting.maxChars", "8")));

            context.register(AppConfig.class);

            BeanDefinition manualDefinition = BeanDefinitionBuilder
                    .genericBeanDefinition(ManualGreeting.class)
                    .addPropertyValue("label", "manual")
                    .addPropertyReference("formatter", "nameFormatter")
                    .getBeanDefinition();

            context.registerBeanDefinition(
                    "manualGreeting", manualDefinition);
            context.refresh();

            NameFormatter formatter = context.getBean(NameFormatter.class);
            GreetingService service =
                    context.getBean(GreetingService.class);
            ManualGreeting manual = context.getBean(ManualGreeting.class);

            BeanDefinition actual = context.getBeanFactory()
                    .getBeanDefinition("manualGreeting");
            PropertyValue label = actual.getPropertyValues()
                    .getPropertyValue("label");
            PropertyValue propertyReference = actual.getPropertyValues()
                    .getPropertyValue("formatter");
            RuntimeBeanReference reference =
                    (RuntimeBeanReference) propertyReference.getValue();

            System.out.println("propertyPrefix=" +
                    context.getEnvironment().getProperty("greeting.prefix"));
            System.out.println("propertyMaxChars=" +
                    context.getEnvironment().getRequiredProperty(
                            "greeting.maxChars", Integer.class));
            System.out.println("literalMetadata=" + label.getValue());
            System.out.println("referenceMetadata=" +
                    reference.getBeanName());
            System.out.println("sameFormatter=" +
                    (service.formatter() == formatter
                     && manual.formatter() == formatter));
            System.out.println("serviceGreeting=" +
                    service.greet(" Lan "));
            System.out.println("manualGreeting=" +
                    manual.greet(" Lan "));
            System.out.println("manualSingleton=" +
                    (manual == context.getBean(ManualGreeting.class)));
        }
    }
}
~~~

**Analysis of key points:**

- `AppConfig` registers the `nameFormatter` and `greetingService` beans; the service factory method receives the **`NameFormatter` object** along with `Environment`.
- `MapPropertySource` uses `Map.<String, Object>of(...)` (supported in Java 17) to create two non-sensitive in-memory properties. `addFirst(...)` gives demo data priority over other sources with matching keys, keeping results reproducible.
- The factory method reads String `greeting.prefix` and converts `"8"` to `Integer` to pass to the `int maxChars` constructor parameter. **Values do not become beans.**
- `ManualGreeting` has a no-argument constructor and two public setters so Spring can apply property injection from metadata.
- The `manualGreeting` bean is registered **before `refresh()`**, containing one literal value and one explicitly named bean reference.
- `getPropertyValue("formatter")` returns metadata; casting to `RuntimeBeanReference` is controlled because the builder itself set `addPropertyReference(...)`.
- All three uses of the formatter (context lookup, service field, manual field) point to the same managed singleton in this context.
- `GreetingService.greet(" Lan ")` normalizes to `LAN` and prints `Xin chao, LAN!`; `ManualGreeting.greet(...)` prints `manual:LAN`.
- Exiting `try (context)` closes the context. The demo registers no shutdown callback printing to stdout, so no spontaneous shutdown lines appear.

### 6.3. Maven Run Commands

From the `bean-reference-vs-value` directory:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

**Exact eight stdout lines printed by the example's `main` method on a successful run:**

~~~text
propertyPrefix=Xin chao
propertyMaxChars=8
literalMetadata=manual
referenceMetadata=nameFormatter
sameFormatter=true
serviceGreeting=Xin chao, LAN!
manualGreeting=manual:LAN
manualSingleton=true
~~~

JDK/Maven version lines and any framework/build logs **are not part of the eight lines printed by the demo code itself**. There is no randomness, clock dependency, or unstable iteration order in those output values.

### 6.4. Running Manually with `javac` and `java` on Two Operating Systems

Because the source imports Spring, first use Maven to export the dependency classpath:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

**Linux/macOS (bash/zsh):**

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -cp "$(cat classpath.txt)" \
  -d out src/main/java/demo/BeanReferenceVsValueDemo.java
java -cp "out:$(cat classpath.txt)" demo.BeanReferenceVsValueDemo
~~~

**Windows PowerShell:**

~~~powershell
$deps = (Get-Content -Raw classpath.txt).Trim()
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -cp "$deps" -d out src/main/java/demo/BeanReferenceVsValueDemo.java
java -cp "out;$deps" demo.BeanReferenceVsValueDemo
~~~

The classpath entry separator is `:` on Unix and `;` on Windows. Both run the same `demo.BeanReferenceVsValueDemo` class and produce the exact same eight stdout lines from section 6.3.

## 7. Reading Results: Metadata Differs from the Actual Runtime Object

| Output Line | What Is Verified |
| --- | --- |
| `propertyPrefix=Xin chao` | `Environment` supplies the String from the property source |
| `propertyMaxChars=8` | The String config value was converted to the required numeric type |
| `literalMetadata=manual` | `ManualGreeting`'s `BeanDefinition` holds the literal value |
| `referenceMetadata=nameFormatter` | `RuntimeBeanReference` holds the target bean's **name** |
| `sameFormatter=true` | Service and ManualGreeting actually hold the same singleton formatter bean |
| `serviceGreeting=Xin chao, LAN!` | Service combines collaborator object with prefix/maxChars values |
| `manualGreeting=manual:LAN` | Setters received both the literal value and the resolved bean object |
| `manualSingleton=true` | The same singleton bean definition returns the same instance on lookup |

**Do not conflate the two checks:** `referenceMetadata=nameFormatter` only tells you **which bean the metadata points to**; `sameFormatter=true` verifies **the actual runtime object reference** after wiring. Both are needed when debugging complex dependency injection.

**Do not extrapolate** that references always share identity across every scope. This is a singleton within one specific context. Prototypes, scoped proxies, or special factories/proxies can change identity and creation-timing assumptions.

## 8. `@Qualifier` Picks Beans; `@Value` Picks Data

There are two distinct kinds of “selection”:

~~~java
@Qualifier("fastFormatter") NameFormatter formatter
~~~

That is an **injection point requesting a bean candidate** matching the qualifier/name `fastFormatter`. It does not read a `fastFormatter` property from `Environment`.

~~~java
@Value("${greeting.prefix}") String prefix
~~~

That is an **injection point wanting a configuration value** for key `greeting.prefix`, not looking up a Spring `String` bean named prefix by the same rules.

If you want multiple beans implementing `NameFormatter`:

~~~java
@Bean("upperFormatter")
NameFormatter upperFormatter() {
    return new UppercaseFormatter();
}

@Bean("otherFormatter")
NameFormatter otherFormatter() {
    return new OtherFormatter();
}
~~~

**This is an illustrative snippet, not standalone runnable because `OtherFormatter` is not defined.** Having two beans of the same type is not invalid; however, single-valued injection `NameFormatter formatter` can become ambiguous if Spring has no clear way to choose. Use `@Qualifier` at the injection point, `@Primary` when a valid default exists, or redesign so only one candidate is needed.

**Do not use `@Qualifier` to fix a missing `greeting.prefix` value.** That is a property configuration error, so inspect the value source. And do not use `@Value("${someBeanName}")` as a substitute for a bean dependency of type `NameFormatter` when the goal is retrieving a managed object.

## 9. Common Simple Value Types and Conversions

It is not only `String`:

| Config Value | Desired Java Type | Check |
| --- | --- | --- |
| `"Xin chao"` | `String` | Is it empty/blank? |
| `"8"` | `Integer`/`int` | Does it convert and exceed 0? |
| `"true"` | `Boolean`/`boolean` | Valid syntax and default policy |
| `"3000"` | `long` | Is the unit (e.g., ms) unambiguous? |
| `"MAIL"` | Enum `Channel` if defined | Does it match an enum constant? |
| `"https://example.org"` | `URI` if conversion supports it | Does it have a valid scheme/host? |

Spring provides property resolution and type conversion mechanisms, yet **successful conversion does not mean the value is business-valid**. For example, `maxChars=-5` converts cleanly to `int`; the constructor must reject it for violating an invariant.

`Environment` values can come from:

- JVM system properties or environment variables.
- `MapPropertySource`, `.properties` files registered via an appropriate mechanism, or property sources added by a hosting framework.
- Spring Boot adds its own external configuration mechanisms, whereas this lesson runs plain Spring Framework; **do not assume an `application.properties` file is automatically loaded as in Boot**.

**Property source order matters:** a higher-precedence source wins when keys collide. The demo uses `addFirst` to keep results deterministic, not as a universal rule that every application should prioritize an in-memory map.

### Missing Values and Optional Values

Use `getRequiredProperty(key)` when configuration is mandatory. If the key is missing, the container fails while creating the dependent bean — far better than silently using an empty string or zero.

When a value is genuinely optional, you can supply a default via `Environment.getProperty(key, defaultValue)` or a property placeholder with a suitable fallback. Defaults must carry clear business meaning and be documented; **never use defaults to mask misconfiguration**.

If a value is a secret (password/token), never hardcode it or print it to stdout/logs. Being sensitive does not turn a secret into a Spring service bean; storing, passing, and protecting secrets is a separate concern requiring dedicated design.

## 10. Scope, Lifecycle, and Where References Land

| Mechanism | Effect |
| --- | --- |
| Default singleton | Consumers pointing to the same bean definition typically share one object |
| Prototype | Each time Spring creates/serves a prototype request it may yield a new instance |
| Prototype injected into singleton | Typically resolved once when the singleton is created, not swapped on every method call |
| `@Lazy` | May defer instantiation; does not remove the logical dependency |
| `ObjectProvider<NameFormatter>` | Allows on-demand bean retrieval, suitable for dynamic lookup |
| Bean alias | An alternate name for the same bean; does not create a separate object just for the alias |
| `new UppercaseFormatter()` outside container | Plain Java object; does not automatically receive managed-bean lifecycle |

**Simple configuration values are typically copied/read at initialization time.** Mutating a property source after a singleton service has been constructed does not automatically update the service's `final String prefix` field. If runtime updates are required, design an explicit mechanism (reconfiguration, recreating beans/contexts, or a suitable mutable contract).

**References are not the same as values**, yet both can cause bugs if shared improperly: a singleton collaborator holding mutable state must be thread-safe under concurrent calls; simple values likewise need type and range validation.

## 11. Common Errors and Diagnosis

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` | No compatible `NameFormatter` bean or wrong reference name | Register the collaborator / verify the bean name |
| `UnsatisfiedDependencyException` | Constructor/factory needs a bean the container cannot resolve | Check type, qualifier, scanning, and dependencies |
| `NoUniqueBeanDefinitionException` | Multiple beans share the type with no single winner | Use `@Qualifier`/`@Primary` or redesign |
| `getRequiredProperty(...)` throws exception | Missing required property key | Check Environment, key spelling, and property sources |
| String property fails to convert to int | Malformed data or incompatible conversion | Check type/property value and validation |
| Bean is created yet constructor rejects maxChars | Value has valid type yet violates invariant | Fix the configured value; do not remove the guard |
| `NotWritablePropertyException` | JavaBean setter does not exist or is misnamed | Declare `setFormatter(...)`/`setLabel(...)` properly |
| `addPropertyValue("formatter", "nameFormatter")` | Confused String bean name with object reference | Use `addPropertyReference(...)` |
| `@Value` receives literal unexpanded placeholder string | Property source/resolver not configured properly | Check context resolution, key presence, and syntax |
| Context refresh PASSES yet behavior is wrong | Wrong bean/value wired or logic bug | Check both runtime identity and output, not just startup |
| Singleton bean retains stale configuration | Property source changed after singleton was created | Implement an explicit refresh/reconfiguration strategy |
| `javac` reports missing Spring API | Classpath lacks Spring JARs and dependencies | Check Maven pom, `-cp`, or classpath file |
| Using bean name as password/config secret | Wrong classification and security practice | Use proper value sources and protect secrets |
| Reference points to a bean whose lifecycle ended | Using object after context shutdown | Respect context ownership and lifecycle |

**Short debugging workflow:** identify the failing parameter; ask whether it is a **value** or a **collaborator bean**; check the corresponding key/property source or type/name/qualifier; read the `Caused by` chain; verify metadata, then inspect the wired runtime object.

## 12. Two Complementary Testing Layers

**Plain Java unit test** verifies logic without Spring:

~~~java
NameFormatter fake = name -> "TEST";
GreetingService service = new GreetingService(fake, "Hello", 10);
System.out.println(service.greet("anything")); // Hello, TEST!
~~~

This is a **snippet** that can live in a method/class with access to the example types; it is not a standalone runnable file. It tests service behavior and collaborator substitution.

**Spring context smoke test** verifies actual wiring:

~~~java
try (AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext()) {
    context.getEnvironment().getPropertySources().addFirst(
            new MapPropertySource("test", Map.<String, Object>of(
                    "greeting.prefix", "Test",
                    "greeting.maxChars", "10")));
    context.register(AppConfig.class);
    context.refresh();

    GreetingService service = context.getBean(GreetingService.class);
    NameFormatter formatter = context.getBean(NameFormatter.class);
    if (service.formatter() != formatter) {
        throw new IllegalStateException("wrong bean reference");
    }
}
~~~

This is **a snippet within a context having full imports and types**, not a second file to run. The check tests reference equality against the expected bean. With other proxies or scopes, adapt checks to the actual contract rather than applying identity tests mechanically.

Worthwhile negative tests in separate setups: missing `greeting.prefix` property, `greeting.maxChars=0`, missing `NameFormatter` bean, two formatter candidates without qualifiers, or mistakenly using `addPropertyValue` instead of a reference. When a test expects failure, assert the **exception type/cause** rather than hardcoding verbatim stack traces, as wrappers/messages can vary across versions.

Do not use Java's default `assert` as a mandatory check because it can be disabled when the JVM runs without `-ea`; use test framework assertions or explicit `if`/exception checks to fail cleanly.

## 13. Practice Exercises with Answers

**Exercise 1.** In constructor `GreetingService(NameFormatter formatter, String prefix, int maxChars)`, which parameter is a bean collaborator?

**Answer:** `formatter`. The other two parameters are simple configuration values; they must be supplied explicitly by the caller or configuration mechanism rather than automatically resolved as beans by name.

**Exercise 2.** Why does `@Qualifier("nameFormatter")` differ from `@Value("${greeting.prefix}")`?

**Answer:** Qualifier constrains **bean candidate selection**; Value requests **resolving configuration data** to pass into the parameter. They do not replace each other.

**Exercise 3.** Is `RuntimeBeanReference("nameFormatter")` itself the running `UppercaseFormatter` object?

**Answer:** No. It is metadata carrying the target name. The container resolves it during wiring; the actual object lands in the consumer's field.

**Exercise 4.** Does adding a `String` bean named `greeting.prefix` automatically make `Environment.getRequiredProperty("greeting.prefix")` read that bean?

**Answer:** No. Property resolution reads **`PropertySource`s**; the bean registry is a separate mechanism. To read values via `Environment`, register an appropriate property source.

**Exercise 5.** Does `addPropertyValue("formatter","nameFormatter")` pass a bean object to `setFormatter(NameFormatter)`?

**Answer:** Not under the semantics defined in this lesson. That is a String literal; to inject a bean object, use `addPropertyReference` or an appropriate bean-resolution mechanism.

**Exercise 6.** Property `greeting.maxChars` has value `"-1"`. If conversion to `Integer` succeeds, is the configuration valid?

**Answer:** Not yet. The `GreetingService` constructor requires a positive `maxChars` and rejects `-1`. Conversion and domain validation are two separate steps.

**Exercise 7.** Why is `sameFormatter=true` in the demo?

**Answer:** Both Service and ManualGreeting receive the singleton `nameFormatter` bean within the same context, and the identity check compares against that exact object. Do not extrapolate this result to every prototype or scoped proxy.

**Exercise 8.** If the environment changes `greeting.prefix` after the singleton service has been created, does the `prefix` field update immediately?

**Answer:** Not automatically; the field was passed into the constructor at initialization. Runtime updates require an explicitly designed update mechanism.

## 14. Application Checklist

- [ ] Identify whether each constructor/factory argument is a bean reference or a simple value.
- [ ] Never equate a bean name String with a managed bean object.
- [ ] Use factory method parameters for collaborators and `Environment`/`@Value` for data values.
- [ ] Do not automatically autowire primitives/`String` as collaborators unless intentionally designed.
- [ ] Use `BeanDefinitionBuilder.addPropertyValue` for literals.
- [ ] Use `addPropertyReference` for bean names that must resolve to objects.
- [ ] Distinguish `RuntimeBeanReference` (metadata) from the injected field (runtime).
- [ ] Ensure setters/constructors match in name, type, and writability.
- [ ] Register bean definitions and property sources before `refresh()` in the demo.
- [ ] Apply required-value policies and contract validation to configuration data.
- [ ] Disambiguate multiple bean candidates with `@Qualifier`/`@Primary` properly.
- [ ] Check scope/lifecycle if identity or creation timing differs from assumptions.
- [ ] Never log secrets and avoid turning every simple value into its own bean.
- [ ] Run Java 17+ with Maven or `javac`/`java` and verify the exact eight stdout lines.
- [ ] Test Java behavior and Spring wiring/configuration separately.

**Conclusion:** A **bean reference** is a relationship between managed objects resolved by Spring by name/type. A **simple value** is data passed into a bean, either literal or resolved from configuration. Although both meet in constructors/setters, they differ in **source, metadata, and how the container resolves them**. Understanding this boundary keeps DI clear, avoids confusing bean-name strings with collaborators, and enables accurate configuration testing.

### Official Spring Documentation

- [Dependency Injection and Collaborators](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-collaborators.html)
- [Using @Bean](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html)
- [Using @Value](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/value-annotations.html)
- [Environment and PropertySource](https://docs.spring.io/spring-framework/reference/6.2/core/beans/environment.html)
