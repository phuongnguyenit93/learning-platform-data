# Providing Arguments via `constructor-arg` in Spring XML Core Container

## 1. Lesson Objectives

In Spring Framework, **constructor injection** is a form of Dependency Injection (DI) where the container creates an object by calling a constructor with resolved arguments. When configuring beans in XML, the **`<constructor-arg>`** element describes the values or references to pass to the constructor (and for factory methods, the corresponding factory arguments).

Simple example:

```xml
<bean id="catalogRepository"
      class="demo.CatalogRepositoryImpl"/>

<bean id="catalogService"
      class="demo.CatalogService">
    <constructor-arg ref="catalogRepository"/>
    <constructor-arg value="CATALOG"/>
</bean>
```

This is an **illustrative example** requiring `demo.CatalogRepositoryImpl` and `demo.CatalogService` to be defined with compatible constructors. Spring does not merely “insert XML into Java”; it reads bean definitions, resolves dependencies, and calls the appropriate constructor to create the bean.

This lesson helps you:

1. Understand the difference between `<constructor-arg ref="..."/>` and `<constructor-arg value="..."/>`.
2. Know how Spring selects constructors and maps arguments by **position**, **type**, or **parameter name**.
3. Use `index` (0-based), `type`, and `name` to eliminate ambiguity.
4. Understand the requirements for using `name` with Java 17: the `-parameters` compiler option or the JDK `@ConstructorProperties` annotation.
5. Use nested `<ref>`, `<value>`, `<null/>`, `<list>`, `<map>`, and inner beans when needed.
6. Know the **`c:` namespace** shorthand and the difference between `c:_0-ref` and `c:name-ref`.
7. Distinguish constructor injection, setter/property injection, and XML constructor autowiring.
8. Understand how Spring converts XML strings into `int`, `long`, `boolean`, enums, or types with compatible conversions.
9. Recognize overloaded constructors, null ambiguity, missing beans, cycles, and common initialization errors.
10. Run a complete example with **Java 17 + Spring Framework 6.2.x**; verify dependency identity and stdout.
11. Design readable XML when combining with Java configuration, XML imports, scopes, and lifecycle.
12. Know how to test, debug, and migrate to Java-based configuration while preserving the dependency contract.

**Key takeaway:** `<constructor-arg>` represents the **bean instantiation contract**. It is not a setter, not a Java variable name, and not an instruction to invoke the constructor immediately when the XML file is parsed.

## 2. How Does Constructor Injection Work?

Java example:

```java
package example;

public final class ShippingService {
    private final ShippingRepository repository;

    public ShippingService(ShippingRepository repository) {
        this.repository = repository;
    }

    public String dispatch(String trackingCode) {
        return repository.saveTracking(trackingCode);
    }
}
```

This snippet is not standalone: it requires defining the `ShippingRepository` interface with a `saveTracking` method. The `ShippingService` class explicitly declares that it **requires a repository** right at its constructor. It does not call `new ShippingRepositoryImpl()` internally, nor does it query the BeanFactory by string name.

XML declaration:

```xml
<bean id="shippingRepository"
      class="example.InMemoryShippingRepository"/>

<bean id="shippingService"
      class="example.ShippingService">
    <constructor-arg ref="shippingRepository"/>
</bean>
```

Inside an `ApplicationContext` reading this XML, Spring conceptually performs:

```text
Read XML <bean id="shippingService">
                  |
                  v
BeanDefinition shippingService
  beanClass = example.ShippingService
  constructorArgs = [ref(shippingRepository)]
                  |
                  v
BeanFactory needs to create shippingService
                  |
                  v
Resolve bean shippingRepository
                  |
                  v
Select matching constructor
                  |
                  v
new ShippingService(managedRepository)
                  |
                  v
Apply bean initialization/post-processors
                  |
                  v
Managed bean shippingService
```

If `shippingRepository` is a default singleton, the instance passed into `ShippingService` is the object managed by the **same BeanFactory**. The constructor dependency graph also dictates the necessary initialization order: to build the service, Spring must resolve the repository first.

### Why Is Constructor Injection Often Preferred?

- Required dependencies are **visible directly in the class API**.
- Enables `final` fields; the object reaches a valid state earlier.
- Fails fast when a collaborator is missing instead of creating a half-initialized bean.
- Unit tests can invoke the constructor with a fake/stub without starting Spring.
- Reduces the chance of forgetting to call a setter.
- Makes the dependency graph easier to analyze and detect cycles in.

Constructor injection does not guarantee everything works automatically. If two constructors depend on each other, Spring cannot complete creation; or if overloaded constructors/values are unclear, the XML needs disambiguation.

## 3. Standard Syntax of `<constructor-arg>`

A typical Spring XML configuration:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
          http://www.springframework.org/schema/beans
          https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="backend" class="example.MemoryBackend"/>

    <bean id="gateway" class="example.Gateway">
        <constructor-arg ref="backend"/>
        <constructor-arg value="production"/>
    </bean>

</beans>
```

Two common attribute forms:

| Syntax | What does Spring receive? | Example |
| --- | --- | --- |
| `ref="beanName"` | Reference to **another bean** in the container | `<constructor-arg ref="backend"/>` |
| `value="text"` | **Character string**, converted to the constructor parameter type | `<constructor-arg value="15"/>` |
| `index="0"` | Parameter position in the constructor, **0-based** | `<constructor-arg index="0" ref="backend"/>` |
| `type="int"` | Parameter type hint for constructor selection/matching | `<constructor-arg type="int" value="15"/>` |
| `name="timeout"` | Matches by Java constructor parameter name | `<constructor-arg name="timeout" value="15"/>` |

`Gateway` and `MemoryBackend` are illustrative types, not part of the complete runnable project below.

Inside `<constructor-arg>`, you can also use **sub-elements**:

```xml
<bean id="gateway" class="example.Gateway">
    <constructor-arg>
        <ref bean="backend"/>
    </constructor-arg>
    <constructor-arg>
        <value>production</value>
    </constructor-arg>
</bean>
```

Here `<ref bean="backend"/>` is equivalent in intent to `ref="backend"`. `<value>production</value>` is equivalent to a string literal. The nested form is useful for collections, inner beans, or long value structures.

**Do not write both `ref` and `value` on the same `<constructor-arg>`** to represent the same parameter. Each argument must have a single clear value or bean reference.

## 4. Distinguishing `ref` and `value` — The Most Important Mistake

Suppose you have the class:

```java
public final class EngineController {
    private final Engine engine;

    public EngineController(Engine engine) {
        this.engine = engine;
    }
}
```

This is an illustration requiring type `Engine`. Correct configuration:

```xml
<bean id="engine" class="example.Engine"/>
<bean id="controller" class="example.EngineController">
    <constructor-arg ref="engine"/>
</bean>
```

The container looks up the bean **named `engine`**, then passes the object to the constructor. If instead you write:

```xml
<constructor-arg value="engine"/>
```

Spring receives the **string `"engine"`**, not a bean. It will attempt to convert the string to the parameter type. For an `Engine` type without a compatible converter, bean creation fails; in some projects with custom converters, the string might be converted in an unintended way.

Conversely, when a constructor expects `String endpoint`, XML should use `value="https://example.test"`. Do not use `ref="https://example.test"` if no such bean name exists.

### Nested `<ref>` Form

```xml
<constructor-arg>
    <ref bean="engine"/>
</constructor-arg>
```

Equivalent in reference contract to `<constructor-arg ref="engine"/>`. The referenced bean may be defined in another XML file within the **same ApplicationContext**, or in a parent context per `<ref>` semantics.

### Nested `<idref>` Differs from `<ref>`

```xml
<constructor-arg>
    <idref bean="engine"/>
</constructor-arg>
```

`<idref>` passes the **bean name as a String** after verifying its existence, rather than passing the bean object itself. Suitable for a component that genuinely needs **a bean's name** as a configuration value. If the constructor expects an `Engine` object, use `<ref>`.

### `<null/>` Form

```xml
<constructor-arg>
    <null/>
</constructor-arg>
```

`<null/>` passes Java `null`. Use only when the API explicitly permits null. `null` complicates overload resolution if multiple constructors have compatible reference types; use `index`/`type` or design unambiguous constructors. Never use null to mask a missing required dependency.

## 5. Matching Parameters Without `index`, `type`, or `name`

If a constructor has parameters of **distinct, unambiguous types**, declaration order can be used:

```java
// Illustrative:
public ShipmentPlanner(RouteRepository routeRepository,
                       RateProvider rateProvider) {
}
```

```xml
<bean id="planner" class="example.ShipmentPlanner">
    <constructor-arg ref="routeRepository"/>
    <constructor-arg ref="rateProvider"/>
</bean>
```

Spring can use the type metadata of the references to select the matching parameters. In unambiguous cases, the argument list in order is passed to the corresponding constructor.

Problems arise when **multiple parameters share the same type** or when all values are text from XML. Consider:

```java
public final class ReportOptions {
    private final int maxRows;
    private final String title;

    public ReportOptions(int maxRows, String title) {
        this.maxRows = maxRows;
        this.title = title;
    }
}
```

Two XML values:

```xml
<bean id="options" class="example.ReportOptions">
    <constructor-arg value="100"/>
    <constructor-arg value="Daily"/>
</bean>
```

can be type-converted by Spring when the constructor is unambiguous. However, if there is an overload `ReportOptions(String, int)` or both arguments are numeric strings, the choice can be confusing, depending on conversion and candidate matching. **Do not rely on heuristics when the design has ambiguity**; specify `index`, `type`, or `name`.

## 6. `index`: Direct Mapping by 0-Based Position

`index` tells Spring which parameter position an argument corresponds to:

```java
public ReportOptions(int maxRows, String title) {
    // ...
}
```

```xml
<bean id="options" class="example.ReportOptions">
    <constructor-arg index="1" value="Daily"/>
    <constructor-arg index="0" value="100"/>
</bean>
```

Even though the two tags appear in order 1 then 0, Spring maps them to:

```text
constructor:
   [0] int maxRows       <- "100" -> 100
   [1] String title      <- "Daily"
```

Rules:

- Index is **0-based**, just like Java array indices.
- `index="0"` is the first parameter, `index="1"` is the second.
- Two `<constructor-arg index="0">` elements defining the same position are a configuration metadata error or cause a conflict; do not use it to intentionally override.
- An index outside the matching constructor signature causes a resolution/bean-creation error.
- `index` does not depend on the compiler preserving parameter names, so it remains reliable without `-parameters`.
- `index` is still a **positional contract**. If a developer swaps two parameters of the same type in Java, XML may not catch it at compile time, yet behavior changes.

### When Should You Use `index`?

- Two arguments have the same type `String`.
- The constructor takes `String id, String region`, where order matters.
- Parameter-name metadata cannot be preserved at runtime.
- Using c-namespace positional syntax `c:_0` or `c:_0-ref`.
- Selecting a specific argument for overloaded constructors.

For example, tag order does not matter when `index` is explicit, though for readability in reviews, people usually write them in 0→1→2 order.

## 7. `type`: Disambiguating Parameter Types

`type` specifies the target parameter type Spring should match, which is especially helpful when literal values do not reveal their type on their own.

```java
public final class CalculationSettings {
    public CalculationSettings(int attempts, String label) {
        // ...
    }
}
```

```xml
<bean id="calculationSettings" class="example.CalculationSettings">
    <constructor-arg type="int" value="3"/>
    <constructor-arg type="java.lang.String" value="gold"/>
</bean>
```

Java primitive names like `int`, `long`, and `boolean` are used directly; reference types can use fully qualified names like `java.lang.String`. Spring converts `value="3"` to `int` when selecting/invoking the constructor.

### `type` Is Not a “New Object Type”

`type="java.lang.String"` **does not declare a standalone String bean**. It only hints at the parameter signature of the constructor to call. The bean object created still has the class specified in `<bean class="...">`.

### Numeric Types Are Easy to Confuse

Suppose a class has overloads:

```java
// Illustrative, do not place with the runnable example.
public Limits(int max, long delayMillis) {
}
public Limits(long max, int delayMillis) {
}
```

XML:

```xml
<constructor-arg value="5"/>
<constructor-arg value="1000"/>
```

contains two numeric strings, so it does not clearly indicate which overload is intended. Use `index` together with `type` (or better yet, design an unambiguous constructor) to give Spring clear information.

### Combining `type` and `ref`

You can specify `type` alongside `ref` if it helps disambiguate an overload. Nevertheless, for bean references whose type Spring already knows, repeating `type` is usually **unnecessary**. Redundant metadata makes XML verbose and fragile when refactoring interfaces/implementations.

## 8. `name`: Mapping by Constructor Parameter Name

Instead of position, XML can write:

```java
public final class RetrySettings {
    public RetrySettings(int maxAttempts, long delayMillis) {
    }
}
```

```xml
<bean id="retrySettings" class="example.RetrySettings">
    <constructor-arg name="delayMillis" value="1500"/>
    <constructor-arg name="maxAttempts" value="3"/>
</bean>
```

The names `delayMillis`/`maxAttempts` must match the parameter-name metadata that Spring sees. Unlike `index`, the XML source is self-describing regarding each argument's **meaning** and independent of tag order. However, **Java parameter names are not preserved in every build by default**.

### 8.1. Compiling with `-parameters`

From Java 8 onward, `javac -parameters` retains parameter names in bytecode so reflection/Spring can read them. With Java 17:

```bash
javac -parameters RetrySettings.java
```

If using Maven, configure `maven-compiler-plugin`:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>17</release>
        <parameters>true</parameters>
    </configuration>
</plugin>
```

The runnable example in Section 13 uses this Maven configuration; because of it, `<constructor-arg name="maxAttempts">` works with explicit metadata.

### 8.2. `@ConstructorProperties` When Not Using `-parameters`

Spring also recognizes constructor argument names declared via **`@ConstructorProperties`** from the JDK:

```java
import java.beans.ConstructorProperties;

public final class RetrySettings {
    private final int maxAttempts;
    private final long delayMillis;

    @ConstructorProperties({"maxAttempts", "delayMillis"})
    public RetrySettings(int maxAttempts, long delayMillis) {
        this.maxAttempts = maxAttempts;
        this.delayMillis = delayMillis;
    }
}
```

The annotation must reflect the **exact order of the constructor parameters**. Unlike `@Autowired`, it requires no Spring dependency in the domain class, because `@ConstructorProperties` lives in `java.beans`.

### 8.3. What If Name Metadata Is Missing?

XML `name="maxAttempts"` may fail to match the constructor as expected and bean creation fails. Solutions:

- Enable `-parameters` (recommended in modern Java builds when relying on parameter-name metadata).
- Use `@ConstructorProperties` if you want to keep the contract explicit in source code.
- Or use `index` instead of `name` if you cannot control compiler settings.

Do not fix the error by guessing different `name` values until startup succeeds; inspect the actual runtime names and relevant overloads.

### 8.4. Difference Between XML `name` and Bean `id`

In:

```xml
<bean id="retrySettings" class="example.RetrySettings">
    <constructor-arg name="maxAttempts" value="3"/>
</bean>
```

`retrySettings` is the **bean name in the container**; `maxAttempts` is the **parameter name inside the Java constructor**. One is for bean lookup, the other for argument matching. Never swap them.

## 9. Which Should You Choose: `index`, `type`, or `name`?

| Situation | Helpful choice | Limitation |
| --- | --- | --- |
| Dependencies of distinct types, low risk of confusion | `<constructor-arg ref="..."/>` in order | Must keep all arguments present |
| Two `String` parameters with different meanings | `index` or `name` | `index` depends on position; `name` depends on metadata |
| Numeric literals for overloaded constructors | `type`, combined with `index` if needed | More verbose metadata; valid overload must still exist |
| Want XML to self-describe argument semantics | `name` | Requires `-parameters` or `@ConstructorProperties` |
| Cannot control compiler flags | `index` | Refactoring Java parameter order can cause regressions |
| An argument is another Spring bean | `ref` | Referenced bean must exist and have a compatible type |
| An argument is a literal | `value` | Spring must convert it; format must be valid |
| An argument is a list/map | Nested `<list>`/`<map>` | Generic conversion/ordering should be verified |
| Intentionally null value | Nested `<null/>` | Easily ambiguous with overloaded reference parameters |

**Best practice:** For complex constructors, the optimal choice is usually to **reduce overload ambiguity on the Java side**, then write clear XML for human readers. Do not turn XML into a maze of `index`/`type` attributes to compensate for a confusing constructor API.

## 10. Constructor Overloads and Selection Rules

In Java, a class can have multiple constructors:

```java
// Illustrative overloaded API.
public final class EndpointClient {
    public EndpointClient(String url) { /* ... */ }
    public EndpointClient(String url, int timeoutMillis) { /* ... */ }
    public EndpointClient(URI uri, int timeoutMillis) { /* ... */ }
}
```

This requires importing `java.net.URI`. With XML:

```xml
<bean id="endpointClient" class="example.EndpointClient">
    <constructor-arg value="https://example.test"/>
    <constructor-arg value="1000"/>
</bean>
```

Spring evaluates argument counts, types, conversions, and available metadata to find a matching constructor. You should not assume that “the first declared constructor” or “the longest constructor” is always chosen regardless of metadata.

### Disambiguating Overloads with `index`/`type`

```xml
<bean id="endpointClient" class="example.EndpointClient">
    <constructor-arg index="0"
                     type="java.lang.String"
                     value="https://example.test"/>
    <constructor-arg index="1"
                     type="int"
                     value="1000"/>
</bean>
```

This makes the intent to select `EndpointClient(String, int)` clearer. If the declared type does not match any valid overload, Spring reports an error; metadata cannot force the JVM to run a nonexistent constructor.

### Designing DI-Friendly APIs

If you own the source class, consider:

- One primary constructor with required dependencies.
- Grouping primitive/string settings into an **immutable settings object** when many parameters share the same type.
- Using a builder or named static factory when different configurations have distinct semantics.
- Keeping legacy overloads only for compatibility and testing which signature Spring selects.

**Separating implementation choice from primitive configuration:** Instead of a class with dozens of overloads, extract `EndpointSettings` as a separate bean, then pass that settings bean via `ref` into the client constructor.

## 11. Passing Multiple Bean References and Mixing with `value`

A bean can require both a collaborator object and literals:

```java
// Illustrative:
public final class NotificationService {
    public NotificationService(MessageGateway gateway,
                               String sender,
                               int retries) {
    }
}
```

XML:

```xml
<bean id="gateway" class="example.DefaultMessageGateway"/>

<bean id="notificationService" class="example.NotificationService">
    <constructor-arg index="0" ref="gateway"/>
    <constructor-arg index="1" value="no-reply"/>
    <constructor-arg index="2" value="3"/>
</bean>
```

Spring resolves `gateway` to a `MessageGateway`-compatible bean, while `no-reply` and `3` are literal values; conversion turns `"3"` into `int`.

### Lifecycle and Dependency Identity

A `ref` requests a managed bean. If the referenced bean is a default singleton, Spring typically passes **the same instance** to all matching consumers in the same `ApplicationContext`.

If you write:

```java
NotificationService service =
        new NotificationService(new DefaultMessageGateway(), "no-reply", 3);
```

outside the container, you construct a separate object unrelated to the managed singleton. That is normal Java construction and does not verify XML DI.

### Missing Bean Reference

If `ref="gateway"` has no matching bean/alias to resolve, Spring normally throws a dependency resolution or bean creation error. Do not change `ref` to `value` just to make XML parse; that completely changes the data's meaning.

## 12. Passing Collections, Inner Beans, and Property-Like Values

Constructor parameters are not always scalars or single beans.

### 12.1. `List<String>`

Suppose the Java constructor is:

```java
// Illustrative:
public AllowedRegions(java.util.List<String> regions) {
}
```

XML:

```xml
<bean id="allowedRegions" class="example.AllowedRegions">
    <constructor-arg>
        <list>
            <value>ap-southeast-1</value>
            <value>eu-west-1</value>
            <value>us-east-1</value>
        </list>
    </constructor-arg>
</bean>
```

Spring supplies the collection when creating the bean; `List<String>` generic metadata helps convert elements by type. For `List<Handler>`, `<ref bean="..."/>` is typically used inside `<list>`.

### 12.2. `Map<String, Integer>`

```java
// Illustrative:
public ThrottleLimits(java.util.Map<String, Integer> perRegion) {
}
```

```xml
<bean id="throttleLimits" class="example.ThrottleLimits">
    <constructor-arg>
        <map>
            <entry key="ap-southeast-1" value="10"/>
            <entry key="eu-west-1" value="20"/>
        </map>
    </constructor-arg>
</bean>
```

Spring can convert the strings `10` and `20` to `Integer` using the constructor's generic type metadata. This registers a single `ThrottleLimits` bean containing a map; it does not mean Spring registers extra beans named `ap-southeast-1`.

### 12.3. Inner Bean

```xml
<bean id="filterService" class="example.FilterService">
    <constructor-arg>
        <bean class="example.DefaultFilterPolicy">
            <constructor-arg value="strict"/>
        </bean>
    </constructor-arg>
</bean>
```

`DefaultFilterPolicy` is an **inner bean definition** created exclusively for the outer bean; it needs no `id` and cannot be retrieved independently via `getBean("defaultFilterPolicy")`. An inner bean's lifecycle is tied to the outer bean, rather than being a public singleton shared across the application.

When multiple consumers need the same policy bean, it is better to register a **named bean** and use `ref` rather than duplicating inner beans.

### 12.4. Null vs. Empty Literal

```xml
<constructor-arg>
    <null/>
</constructor-arg>
```

passes `null`, whereas:

```xml
<constructor-arg value=""/>
```

passes an empty string `""` (or corresponding converted value). Do not treat these two as equivalent. For required inputs, validate in the constructor instead of silently accepting `null`.

## 13. Complete Runnable Example: Java 17 + Spring Framework 6.2

This example does not use Spring Boot, a database, or an external API. We declare all beans in XML to demonstrate `<constructor-arg>`, while keeping Java classes as Spring-independent POJOs.

What the example verifies:

- `ref` and `index`: `CatalogService` receives the exact `Catalog` singleton.
- `value`: passes prefix `SKU-` into the constructor.
- `name`: `RetrySettings` receives `maxAttempts` and `delayMillis` from XML; Maven enables `-parameters`.
- `type`: `AuditLabel` receives `String` and `int`.
- `c:` namespace: `Reporter` receives a bean via `c:_0-ref` and a literal via `c:_1`.
- Spring performs `String -> int/long` conversions properly.
- Singleton scope: looking up the repository through the service and directly from the context yields the same reference.

### 13.1. Project Structure

```text
xml-constructor-args/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── XmlConstructorArgsDemo.java
        └── resources/
            └── beans.xml
```

### 13.2. Create `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
             http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>xml-constructor-args</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
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
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                    <parameters>true</parameters>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 13.3. Complete Java Source

Create `src/main/java/demo/XmlConstructorArgsDemo.java`:

```java
package demo;

import org.springframework.context.support.ClassPathXmlApplicationContext;

public class XmlConstructorArgsDemo {

    public interface Catalog {
        String find(String sku);
    }

    public static final class MemoryCatalog implements Catalog {
        public MemoryCatalog() {
        }

        @Override
        public String find(String sku) {
            return switch (sku) {
                case "BK-7" -> "Java book";
                case "MUG-2" -> "Coffee mug";
                default -> "Unknown item";
            };
        }
    }

    public static final class CatalogService {
        private final Catalog catalog;
        private final String prefix;

        public CatalogService(Catalog catalog, String prefix) {
            this.catalog = catalog;
            this.prefix = prefix;
        }

        public String describe(String sku) {
            return prefix + catalog.find(sku);
        }

        public Catalog catalog() {
            return catalog;
        }
    }

    public static final class RetrySettings {
        private final int maxAttempts;
        private final long delayMillis;

        public RetrySettings(int maxAttempts, long delayMillis) {
            this.maxAttempts = maxAttempts;
            this.delayMillis = delayMillis;
        }

        public String describe() {
            return "attempts=" + maxAttempts
                    + ",delayMillis=" + delayMillis;
        }
    }

    public static final class AuditLabel {
        private final String name;
        private final int level;

        public AuditLabel(String name, int level) {
            this.name = name;
            this.level = level;
        }

        public String describe() {
            return name + "#" + level;
        }
    }

    public static final class Reporter {
        private final CatalogService service;
        private final String label;

        public Reporter(CatalogService service, String label) {
            this.service = service;
            this.label = label;
        }

        public String line(String sku) {
            return label + service.describe(sku);
        }

        public CatalogService service() {
            return service;
        }
    }

    public static void main(String[] args) {
        try (var context = new ClassPathXmlApplicationContext("beans.xml")) {
            Catalog catalog = context.getBean(Catalog.class);
            CatalogService service = context.getBean(CatalogService.class);
            RetrySettings retry = context.getBean(RetrySettings.class);
            AuditLabel audit = context.getBean(AuditLabel.class);
            Reporter reporter = context.getBean(Reporter.class);

            System.out.println("service=" + service.describe("BK-7"));
            System.out.println("retry=" + retry.describe());
            System.out.println("audit=" + audit.describe());
            System.out.println("report=" + reporter.line("MUG-2"));
            System.out.println("sameCatalog=" +
                    (catalog == service.catalog()));
            System.out.println("sameService=" +
                    (service == reporter.service()));
        }
    }
}
```

Note on Java types: All classes instantiated directly by XML are **`public static` nested classes** with public constructors. Because of that, Spring does not need an outer `XmlConstructorArgsDemo` instance. In XML, their binary class names use `$`, such as `demo.XmlConstructorArgsDemo$MemoryCatalog`.

### 13.4. Complete Spring XML

Create `src/main/resources/beans.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:c="http://www.springframework.org/schema/c"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <!-- Bean with a public no-arg constructor. -->
    <bean id="catalog"
          class="demo.XmlConstructorArgsDemo$MemoryCatalog"/>

    <!-- Explicit position: constructor CatalogService(Catalog, String). -->
    <bean id="catalogService"
          class="demo.XmlConstructorArgsDemo$CatalogService">
        <constructor-arg index="0" ref="catalog"/>
        <constructor-arg index="1" value="SKU-"/>
    </bean>

    <!-- Name matching: Maven compiler enables -parameters. -->
    <bean id="retrySettings"
          class="demo.XmlConstructorArgsDemo$RetrySettings">
        <constructor-arg name="delayMillis" value="1500"/>
        <constructor-arg name="maxAttempts" value="3"/>
    </bean>

    <!-- Explicit type matching for simple values. -->
    <bean id="auditLabel"
          class="demo.XmlConstructorArgsDemo$AuditLabel">
        <constructor-arg type="java.lang.String" value="AUDIT"/>
        <constructor-arg type="int" value="7"/>
    </bean>

    <!-- c-namespace positional shortcut, _0 is the first parameter. -->
    <bean id="reporter"
          class="demo.XmlConstructorArgsDemo$Reporter"
          c:_0-ref="catalogService"
          c:_1="REPORT:"/>
</beans>
```

XML declares five primary beans: `catalog`, `catalogService`, `retrySettings`, `auditLabel`, `reporter`. There is no `@ComponentScan`; in this example Spring creates them because `ClassPathXmlApplicationContext` reads `beans.xml`.

### 13.5. Running

Requires JDK 17+ and Maven. From the directory containing `pom.xml`:

```bash
mvn -q clean compile exec:java -Dexec.mainClass=demo.XmlConstructorArgsDemo
```

Output **printed by the application itself**, excluding environment-dependent Maven/Spring logs:

```text
service=SKU-Java book
retry=attempts=3,delayMillis=1500
audit=AUDIT#7
report=REPORT:SKU-Coffee mug
sameCatalog=true
sameService=true
```

### 13.6. Line-by-Line Explanation

**`service=SKU-Java book`:** XML `catalogService` has `index="0" ref="catalog"`, so Spring passes the managed `MemoryCatalog` to `CatalogService(Catalog, String)`. `index="1" value="SKU-"` passes the prefix literal. `describe("BK-7")` produces `SKU-Java book`.

**`retry=attempts=3,delayMillis=1500`:** The `name="delayMillis"` tag appears first in XML, but Spring maps the parameter names accurately thanks to `-parameters`. The string `"1500"` is converted to `long`; `"3"` is converted to `int`. Thus XML tag order **does not alter meaning** when `name` is explicitly matched.

**`audit=AUDIT#7`:** `type="java.lang.String"` and `type="int"` help Spring match `AuditLabel(String, int)`; literal `7` is converted to `int`.

**`report=REPORT:SKU-Coffee mug`:** `c:_0-ref="catalogService"` passes the Spring-managed `CatalogService` bean, and `c:_1="REPORT:"` passes the string. Reporter uses the service to look up `MUG-2`, returning `Coffee mug`.

**`sameCatalog=true`:** `CatalogService` holds the exact `Catalog` singleton returned by `context.getBean(Catalog.class)`. No new repository object was created via `new` inside the consumer.

**`sameService=true`:** `Reporter` holds the exact `catalogService` singleton, because `c:_0-ref` denotes a bean reference rather than a string. Thus both ways of obtaining the service (directly from the context and via the reporter) yield the same reference within one `ApplicationContext`.

### 13.7. Why Can a Constructor Accept an Interface?

`CatalogService` declares its constructor accepting the `Catalog` interface. XML provides bean `MemoryCatalog`, which implements `Catalog`. Spring resolves the reference named `catalog` and verifies that the object is compatible with the parameter type. That is abstraction-based DI; the consumer does not need to know where the implementation class was declared.

### 13.8. Controlled Experiments

1. Change `value="SKU-"` to `value="ITEM-"`. Both `service` and `report` outputs change prefix without recompiling Java.
2. Swap the order of the two `name` tags in `retrySettings`. With `-parameters` enabled, output remains unchanged.
3. Remove `<parameters>true</parameters>` and run clean compile. `name` matching may fail to resolve as expected once name metadata is gone; fix using `index` or `@ConstructorProperties`.
4. Change `c:_0-ref="catalogService"` to `c:_0="catalogService"`. Now Spring receives a string instead of the managed bean, causing a type conversion or constructor resolution error.
5. Change `index="0" ref="catalog"` to `ref="missingCatalog"`. Spring reports an error because the dependency does not exist.
6. Replace `delayMillis` with a string not convertible to `long`. Context startup fails with a conversion/bean-creation exception.
7. Change `reporter` from singleton to `scope="prototype"` and retrieve it twice to observe instance identity, noting that the referenced service remains singleton unless its own scope changes.

## 14. The `c`-Namespace: Shorthand for Constructor Arguments

Spring supports the `c:` namespace to replace `<constructor-arg>` elements with XML attributes.

Full form:

```xml
<bean id="reporter" class="example.Reporter">
    <constructor-arg index="0" ref="catalogService"/>
    <constructor-arg index="1" value="REPORT:"/>
</bean>
```

Equivalent `c:` form in intent:

```xml
<bean id="reporter"
      class="example.Reporter"
      c:_0-ref="catalogService"
      c:_1="REPORT:"/>
```

You must declare the namespace on the `<beans>` root:

```xml
xmlns:c="http://www.springframework.org/schema/c"
```

`c:` is a Spring shorthand and **needs no separate XSD for the c-namespace**. Nevertheless, the XML file still needs a valid `beans` namespace/schema.

### 14.1. `c:name` and `c:name-ref`

When parameter names are available:

```java
public Reporter(CatalogService service, String label) {
}
```

you can write:

```xml
<bean id="reporter"
      class="example.Reporter"
      c:service-ref="catalogService"
      c:label="REPORT:"/>
```

Here:

- `c:service-ref` represents a **bean reference** for the constructor parameter named `service`.
- `c:label` represents a **literal string** for the parameter named `label`.
- `service` and `label` must match the parameter-name metadata; pay attention to `-parameters` or equivalent metadata declarations.

### 14.2. `c:_0` and `c:_0-ref`

When parameter names are unavailable, or when mapping by position:

```xml
<bean id="reporter"
      class="example.Reporter"
      c:_0-ref="catalogService"
      c:_1="REPORT:"/>
```

The underscore `_` is required in the indexed notation because XML attribute names cannot start with a digit. The first position is `_0`, not `_1`.

### 14.3. Comparing the Two Styles

| Feature | `<constructor-arg>` | `c:` namespace |
| --- | --- | --- |
| Parameter name | `name="service"` | `c:service-ref="..."` |
| Position | `index="0"` | `c:_0-ref="..."` |
| Bean reference | `ref="bean"` | `-ref` suffix |
| Literal | `value="text"` | No `-ref` suffix |
| Inner bean / long list / map | Uses nested XML | Less flexible than nested form |
| Readability with many short config strings | Team preference | Can be more compact |
| Distinguishing reference from literal | Very explicit | Must watch the `-ref` suffix |

If the codebase already standardizes on `<constructor-arg>`, do not mix both styles in one file just to save a few characters. Consistency matters more than each bean using the shortest possible syntax.

### 14.4. Difference from the `p`-Namespace

`p:` applies to **properties/setters**, not constructor arguments. Example:

```xml
<bean id="client" class="example.Client"
      p:timeout="1000"/>
```

requires the class to have a property setter (or compatible property injection); it does not invoke a `Client(int timeout)` constructor. To pass constructor parameters, use `<constructor-arg>` or `c:`.

## 15. Constructor Injection vs. Setter Injection

Constructor-based DI:

```java
public final class PricingService {
    private final TaxPolicy taxPolicy;

    public PricingService(TaxPolicy taxPolicy) {
        this.taxPolicy = taxPolicy;
    }
}
```

```xml
<bean id="pricingService" class="example.PricingService">
    <constructor-arg ref="taxPolicy"/>
</bean>
```

Setter-based DI:

```java
public class PricingService {
    private TaxPolicy taxPolicy;

    public void setTaxPolicy(TaxPolicy taxPolicy) {
        this.taxPolicy = taxPolicy;
    }
}
```

```xml
<bean id="pricingService" class="example.PricingService">
    <property name="taxPolicy" ref="taxPolicy"/>
</bean>
```

These two class snippets are **two alternative design versions**, not meant to share the same name in the same Java file. They are not standalone runnable examples.

| Criterion | Constructor injection | Setter/property injection |
| --- | --- | --- |
| Required dependencies | Explicitly expressed in the constructor | Can be omitted unless validated |
| `final` fields | Easily supported | Typically unsuitable when setters mutate fields after construction |
| Validation immediately upon creation | Easy | May require an init callback |
| Unit tests without Spring | Just invoke the constructor | Must invoke setters |
| Optional configuration | Can use overloads/settings | Setters are sometimes convenient |
| Constructor cycle A↔B | Usually unresolvable | Some setter cycles can be resolved via early references, though refactoring is preferred |
| XML syntax | `<constructor-arg>` | `<property>` or `p:` |

For indispensable dependencies, Spring documentation generally recommends constructor injection. For optional properties of legacy JavaBeans, setter injection can be reasonable. You do not need to force everything into one DI style; focus on preserving invariants and testability.

## 16. XML `autowire="constructor"` vs. Explicit `constructor-arg`

XML supports constructor autowiring:

```xml
<bean id="processor"
      class="example.Processor"
      autowire="constructor"/>
```

Spring attempts to resolve constructor parameters using **type-compatible beans** in the container. If there is a unique matching bean by type, it can be injected automatically.

Compare with:

```xml
<bean id="processor" class="example.Processor">
    <constructor-arg ref="primaryRepository"/>
</bean>
```

With explicit `ref`, the XML immediately declares which instance is selected. With `autowire="constructor"`, the container infers dependencies by type from candidates.

### Benefits and Risks of `autowire="constructor"`

Benefits:

- Reduces repetition of many `<constructor-arg ref="..."/>` elements.
- Can work well when constructors are clear and beans are unique by type.

Risks:

- If no matching bean exists, instantiation can fail.
- If multiple beans share the same type without clear selection, ambiguity occurs.
- Does not autowire `String` and primitive values as collaborator beans from arbitrary literal config values; those should be passed explicitly.
- Adding a bean implementing the same interface in another module can break existing wiring.
- Dependency relationships are less visible in XML, making legacy code harder to maintain.

**Important:** Explicit `<constructor-arg>` settings take precedence over autowiring for declared arguments. If the application has a complex API, explicit constructor arguments are usually easier to review and debug.

## 17. `constructor-arg` with Static and Instance Factory Methods

Spring XML can create beans via a **constructor** or a **factory method**. With factory methods, `<constructor-arg>` can also represent the arguments Spring passes to the factory method (even though the element is still named `constructor-arg`).

### 17.1. Static Factory Method

Illustrative Java:

```java
public final class ClientFactory {
    private ClientFactory() {
    }

    public static ApiClient create(String endpoint, int timeoutMillis) {
        return new ApiClient(endpoint, timeoutMillis);
    }
}
```

XML:

```xml
<bean id="apiClient"
      class="example.ClientFactory"
      factory-method="create">
    <constructor-arg index="0" value="https://example.test"/>
    <constructor-arg index="1" value="1000"/>
</bean>
```

Here Spring **does not call `new ClientFactory(...)`**. It invokes the static method `ClientFactory.create(String, int)`. The two `<constructor-arg>` elements serve as **factory method arguments**.

### 17.2. Instance Factory Method

Illustrative Java:

```java
public final class ClientFactory {
    public ApiClient create(String region) {
        return new ApiClient(region);
    }
}
```

XML:

```xml
<bean id="clientFactory" class="example.ClientFactory"/>

<bean id="apiClient"
      factory-bean="clientFactory"
      factory-method="create">
    <constructor-arg value="ap-southeast-1"/>
</bean>
```

Bean `clientFactory` exists as a managed factory object, while `apiClient` is the bean created via the instance method `create`. These snippets are **separate illustrations** requiring the corresponding API classes; do not mix two `ClientFactory` versions with the same name in one file.

**Do not confuse:** `factory-bean` points to the factory bean object; `factory-method` is the method name; `<constructor-arg>` is the argument. This differs from Spring's `FactoryBean<T>` interface, which has its own product-vs-factory bean contract.

## 18. Type Conversion and Placeholders in `constructor-arg`

XML `value="..."` starts as a string. When creating the bean, Spring inspects the target parameter type metadata and uses its conversion infrastructure to convert it into `int`, `long`, `boolean`, enums, and other types when a compatible converter exists.

```xml
<bean id="retrySettings" class="example.RetrySettings">
    <constructor-arg index="0" value="3"/>
    <constructor-arg index="1" value="1500"/>
</bean>
```

If the signature is `RetrySettings(int, long)`, both literals are converted to numeric types.

### Conversion Failure

```xml
<constructor-arg index="0" value="three"/>
```

does not automatically convert to `int 3`; without a custom converter, Spring reports a type mismatch/conversion/bean-creation error. Do not hide this by changing every constructor parameter to `String` and parsing ad hoc inside business methods.

### Property Placeholders

`<constructor-arg>` can use placeholders:

```xml
<bean id="retrySettings" class="example.RetrySettings">
    <constructor-arg index="0" value="${retry.maxAttempts}"/>
    <constructor-arg index="1" value="${retry.delayMillis}"/>
</bean>
```

You need a mechanism to resolve placeholders, such as `<context:property-placeholder location="classpath:app.properties"/>`, `PropertySourcesPlaceholderConfigurer`, or the application's configuration infrastructure.

Illustrative `app.properties` file:

```properties
retry.maxAttempts=3
retry.delayMillis=1500
```

Placeholders substitute values into metadata; Spring then runs type conversion to produce the actual constructor arguments. **This does not mean** `<constructor-arg>` opens or reads properties files by itself without a processor.

### When Specialized Types Are Needed

For `Duration`, `URI`, or custom value objects, verify the conversion service, property editors, or constructor contract. Do not assume every string automatically converts to arbitrary Java classes. For complex configuration, a **settings bean with a factory method** is clearer and easier to test than scattered parsing.

## 19. Bean Scope, Lifecycle, and Identity

XML constructor arguments reference managed beans, yet concrete behavior also depends on **bean scope**.

### Singleton Dependency

```xml
<bean id="repo" class="example.MemoryRepo"/>

<bean id="serviceA" class="example.ServiceA">
    <constructor-arg ref="repo"/>
</bean>

<bean id="serviceB" class="example.ServiceB">
    <constructor-arg ref="repo"/>
</bean>
```

If both services are created in the same `BeanFactory`, `repo` is singleton by default, so both constructors typically receive **the same repo reference**.

### Prototype Dependency Injected Once into a Singleton

```xml
<bean id="worker" class="example.Worker" scope="prototype"/>

<bean id="scheduler" class="example.Scheduler">
    <constructor-arg ref="worker"/>
</bean>
```

If `scheduler` is a singleton, Spring resolves the prototype `worker` when creating the scheduler, and the scheduler holds onto that reference. Calling methods on the scheduler later does not automatically inject a new worker each time.

To obtain a fresh prototype per job, use `ObjectProvider<Worker>` or a dedicated factory; do not expect declaring `scope="prototype"` alone to replace the object continuously.

### Collaborator Lifecycle

A `ref` to a bean with `init-method` or `destroy-method` allows Spring to manage its lifecycle per its definition. Writing `new MemoryRepo()` inside a service constructor means that auxiliary object **does not receive** Spring lifecycle management from the `repo` bean.

### Inner Bean vs. Shared Named Bean

As shown in Section 12, an inner bean is bound to its outer bean and is not a shared context-wide singleton. If reuse or independent lifecycle management is needed, define a separate named bean and pass it via `ref`.

## 20. Circular Dependencies: A Graph Problem to Fix, Not Just XML Ordering

Constructor injection exposes dependency cycles early. Look at:

```java
public final class ServiceA {
    public ServiceA(ServiceB b) {
    }
}

public final class ServiceB {
    public ServiceB(ServiceA a) {
    }
}
```

XML:

```xml
<bean id="serviceA" class="example.ServiceA">
    <constructor-arg ref="serviceB"/>
</bean>

<bean id="serviceB" class="example.ServiceB">
    <constructor-arg ref="serviceA"/>
</bean>
```

Graph:

```text
serviceA --> serviceB --> serviceA
```

BeanFactory needs B to build A, yet needs A to build B. This is an unresolvable **constructor cycle**. You may see `BeanCurrentlyInCreationException` as the root cause, wrapped in bean creation/dependency exceptions.

### Preferred Fixes

- Extract shared responsibilities into a `SharedPolicy` or `DomainRule` that both services depend on.
- Move orchestration into a third bean above both services instead of having services call each other mutually.
- If one side only needs event notifications, consider application events with clear consistency/idempotency contracts.
- If a dependency truly must be lazy, consider a deliberate provider/proxy, but do not use it to mask an architectural cycle.

### Does Switching to Setter Injection Help?

Some setter/field injection cycles can be resolved by Spring via **early singleton references** if permitted, but this can expose partially initialized objects, create complex interactions with AOP/proxies, and hurt testability. Do not treat it as the default design choice.

### `@DependsOn` Does Not Resolve Cycles

`@DependsOn` only expresses initialization ordering, not replacing required objects. If A depends on B and B depends on A, you create an ordering cycle too; never attempt to fix a cycle by adding `depends-on="..."` or reordering `<bean>` tags in XML.

## 21. Using `@ImportResource` When Migrating XML to Java Config

A Java-centric application can retain XML containing `constructor-arg`:

```java
@Configuration(proxyBeanMethods = false)
@ImportResource("classpath:beans.xml")
public class RootConfig {
    // Other @Bean methods can be declared here.
}
```

This is an **illustrative snippet**; it requires importing `org.springframework.context.annotation.Configuration` and `ImportResource`. When root is registered into `AnnotationConfigApplicationContext`, XML definitions are imported into the **same container**. `ref` attributes can point to beans from Java `@Bean` methods if bean names match.

Example:

```java
@Configuration(proxyBeanMethods = false)
@ImportResource("classpath:legacy-service.xml")
class RootConfig {
    @Bean("reportRepository")
    ReportRepository reportRepository() {
        return new InMemoryReportRepository();
    }
}
```

XML:

```xml
<bean id="reportService" class="example.ReportService">
    <constructor-arg ref="reportRepository"/>
</bean>
```

Spring finds the `reportRepository` bean declared in Java and passes it to `ReportService`'s constructor from XML. No second context is needed, nor a duplicate factory method.

### When Converting `constructor-arg` to `@Bean` Parameters

XML:

```xml
<bean id="catalogService" class="example.CatalogService">
    <constructor-arg ref="catalog"/>
    <constructor-arg value="SKU-"/>
</bean>
```

Equivalent Java config in intent:

```java
@Bean("catalogService")
CatalogService catalogService(Catalog catalog) {
    return new CatalogService(catalog, "SKU-");
}
```

Spring injects `Catalog` into the factory method parameter; Java code passes the literal to the constructor. Ensure **no XML bean definition with the same name remains** once moved to Java to avoid unintended name collisions or overriding.

### Preserving Contracts During Migration

If XML used constructor `index`/`type`/`name`, verify that the new Java factory still passes arguments with the right semantics, especially with multiple `String` or enum settings. Do not assume compilation success alone is sufficient: migration can alter default values, profiles, or lifecycle behavior invisible to the compiler.

## 22. Debugging `constructor-arg` Errors by Symptom

| Symptom | Likely cause | How to fix |
| --- | --- | --- |
| `BeanCreationException` saying no matching constructor found | Argument count/types do not match constructor | Check actual signature, `index`/`type`/`name`, and class package |
| `UnsatisfiedDependencyException` | Ref to missing bean or dependency chain initialization failure | Check bean definitions and root cause |
| `NoSuchBeanDefinitionException` | `ref="..."` points to a nonexistent bean name | Fix bean id/alias; import the proper config |
| `BeanCurrentlyInCreationException` | Constructor cycle or early bean creation | Draw the dependency graph and split responsibilities |
| `BeanNotOfRequiredTypeException` | Ref exists but type is incompatible or proxy exposes different interface | Align interface/bean type |
| `TypeMismatchException`/conversion error | `value` cannot be converted to parameter type | Fix literal, type, or converter |
| `constructor-arg name` does not match | Build lacks `-parameters` or `@ConstructorProperties` is wrong | Enable metadata or use `index` |
| Wrong/ambiguous overloaded constructor chosen | Multiple candidates accept string/number literals | Use `type`/`index` or clarify the API |
| Two `String` values swapped | Neither `index` nor `name` specified | Set `index="0"/"1"` or `name` with metadata |
| Index out of bounds | `index` exceeds valid parameter count | Check constructor argument count |
| Duplicate index | Two tags specify the same position | Remove duplicate; one value per parameter |
| `c:_0-ref` replaced by `c:_0` | String literal passed instead of bean ref | Add the `-ref` suffix |
| XML `c`-namespace not recognized | Missing `xmlns:c` | Declare the `c` namespace on `<beans>` |
| Bean class not found | Wrong FQCN or missing JAR | Fix dependency and classpath |
| Nested class in XML fails to instantiate | Used dot instead of `$` or missing `public`/`static` | Use binary class name and a valid constructor |
| Output changes after refactoring parameter order | Used `index` while constructor parameter order changed | Update XML alongside refactoring or use name metadata |
| App runs in IDE but fails after packaging | XML missing from runtime resources classpath | Check `src/main/resources` and JAR contents |
| Bean created unexpectedly early | Eager singleton or required collaborator | Check lazy/scope/dependency graph |
| Missing placeholder | Property processor/source not declared | Check `Environment` and configurer |
| Wrong singleton/prototype behavior | Confused `ref` with inner bean or scope | Check bean definitions and lifecycle |

### Ordered Debugging Process

1. Verify the XML file was read by `ApplicationContext` and the bean name is registered.
2. Verify `class="..."` exists, is a suitable type, and can be instantiated by Spring.
3. Inspect all constructors of the class; check argument counts and overloads.
4. Check whether `<constructor-arg>` declares `index`, `type`, or `name`; do not assume Spring matches by tag order in every case.
5. Verify `ref` points to the right bean name and type; do not confuse it with `value`.
6. For `name`, verify Maven/Javac has `-parameters` or `@ConstructorProperties`.
7. For literals, check whether conversion can succeed for the required type.
8. Check scope/proxies and whether the consumer needs a singleton or prototype.
9. If there is a cycle, sketch the constructor dependency graph rather than sprinkling `@DependsOn`/`@Lazy` blindly.
10. Test with a real `ApplicationContext`; inspect the root cause rather than only the wrapper message.

## 23. Testing and Safety Checks for XML Configuration

### 23.1. Testing with `ApplicationContext`

A small program can start the context and assert:

```java
// Additional snippet placed inside main while context is still open.
Catalog catalog = context.getBean(Catalog.class);
CatalogService service = context.getBean(CatalogService.class);

if (catalog != service.catalog()) {
    throw new AssertionError("Expected same managed Catalog singleton");
}
if (!"SKU-Java book".equals(service.describe("BK-7"))) {
    throw new AssertionError("Wrong constructor arguments");
}
```

This is an **extension snippet** of `XmlConstructorArgsDemo.java`, not a standalone program.

### 23.2. Testing XML Bindings by Name

For `RetrySettings`, try swapping the two `name` tags (without changing values) and comparing output. This test proves `name` mapping is order-independent when metadata is present.

Similarly, with `index`, swap the XML tag order while keeping `index="0"/"1"`. The result must remain identical because parameter positions are explicit.

### 23.3. Negative Tests

Create separate test contexts for each failure case:

- Nonexistent bean ref.
- Invalid primitive conversion.
- Duplicate index.
- Ambiguous overloaded constructors.
- Cycle A→B→A.
- XML `c`-namespace missing prefix declaration.
- Constructor `name` mapping missing metadata.
- Inner bean looked up as a named bean.

**Do not modify production config files to test failures.** Use test resource copies or embedded test configurations and assert that context startup fails for the expected reason. Exact exception messages may change across Spring versions; tests should assert exception types/key causes rather than full stack trace strings.

### 23.4. Unit Testing Without Spring

If a business class depends only on interfaces:

```java
Catalog fake = sku -> "Fake item";
CatalogService service = new CatalogService(fake, "TEST-");

if (!"TEST-Fake item".equals(service.describe("anything"))) {
    throw new AssertionError("Unexpected service output");
}
```

This snippet fits within the demo class where `Catalog`/`CatalogService` already exist. It needs no XML/BeanFactory because unit tests verify business logic; integration tests verify `<constructor-arg>` wiring.

### 23.5. Avoid Opening Contexts Repeatedly or Forgetting to Close

In plain Spring Framework:

```java
try (var context = new ClassPathXmlApplicationContext("beans.xml")) {
    // Look up and verify beans.
}
```

`try-with-resources` guarantees `close()` on the context. If beans hold files, sockets, or pools, Spring invokes destroy callbacks according to the bean's scope and lifecycle. A test opening multiple contexts creates independent sets of singletons; do not confuse “singleton” with a JVM-wide instance.

## 24. Common Misconceptions

### “`ref` and `value` are both just text, so they are the same”

False. Both are written as XML attribute strings, yet Spring interprets `ref` as a **bean reference** and `value` as a **literal requiring conversion**. Choosing the wrong one changes the entire dependency graph.

### “`index` starts at 1 to be intuitive”

False. `index` is **0-based**. For `Client(String, int)`, `index="0"` is `String` and `index="1"` is `int`.

### “`name` always works because Java source has parameter names”

False. The compiler is not required to include parameter names in runtime metadata unless `-parameters` is configured; alternatively use JDK `@ConstructorProperties` or `index`.

### “`type="int"` creates an `int` bean”

False. `type` only assists constructor argument matching. `<bean class="...">` determines the primary bean class/object.

### “Reordering `<constructor-arg>` never matters”

False if you omit `index`/`name`/`type` and Spring must rely on order to map arguments. When `index` or `name` is explicit, tag presentation order has less impact; even so, XML should be tested after refactoring.

### “`<constructor-arg>` is only for `new Class(...)`”

Not completely. Spring also uses this argument metadata structure for **static/instance factory methods** when a bean is defined via `factory-method` or `factory-bean`.

### “Constructor injection makes Spring automatically instantiate an interface”

No. Spring needs a bean definition or factory providing a compatible implementation of the interface. XML `<constructor-arg ref="catalog"/>` must point to an instantiable bean.

### “A prototype ref in a singleton swaps instances on every request”

False. The constructor is called when the singleton is created; the prototype dependency is resolved once for that constructor call. Dynamic per-use prototypes require a proper lookup factory or provider.

### “If there is a cycle, switch everything to setter injection”

Not recommended. Some setter cycles pass using early references, but the model remains coupled and risks incomplete state. Constructor cycles should be fixed via dependency inversion or a coordinator.

### “`c:_0-ref` and `c:_0` differ only in attribute name”

Semantically false. The `-ref` suffix specifies a **bean reference**; without it, the attribute is a **literal**. Both may look like identical XML strings yet deliver completely different values to the constructor.

### “`@ImportResource` is a separate context”

False. When Java config imports XML inside the same `ApplicationContext`, bean definitions from XML and `@Bean` are managed by the same `BeanFactory`; there is no need to construct a `ClassPathXmlApplicationContext` inside a `@Bean` method.

## 25. Guided Exercises with Answers

### Exercise 1 — Two `String` Parameters

Constructor:

```java
public UserLabel(String firstName, String lastName) { }
```

Write XML that does not depend on tag order.

**Answer:**

```xml
<bean id="userLabel" class="example.UserLabel">
    <constructor-arg index="1" value="Nguyen"/>
    <constructor-arg index="0" value="An"/>
</bean>
```

The constructor receives `firstName = "An"` and `lastName = "Nguyen"`. Index is 0-based.

### Exercise 2 — Bean Reference

XML:

```xml
<bean id="formatter" class="example.Formatter"/>
<bean id="printer" class="example.Printer">
    <constructor-arg value="formatter"/>
</bean>
```

If `Printer(Formatter)` needs the bean object, what must be fixed?

**Answer:** `<constructor-arg ref="formatter"/>`; `value` only passes a string, not the `Formatter` instance.

### Exercise 3 — Type Matching

Constructor `Options(int attempts, String label)`. Write XML clarifying target types.

**Answer:**

```xml
<bean id="options" class="example.Options">
    <constructor-arg type="int" value="4"/>
    <constructor-arg type="java.lang.String" value="fast"/>
</bean>
```

Spring has type metadata to match the right signature and convert literal `4` to `int`.

### Exercise 4 — `name` and Build Metadata

For `RetrySettings(int maxAttempts, long delayMillis)`, XML uses `name`. What does the compiler need?

**Answer:** Enable `javac -parameters`, place `@ConstructorProperties({"maxAttempts","delayMillis"})` on the constructor, or switch to explicit `index` if name metadata cannot be kept.

### Exercise 5 — `c`-Namespace

Convert:

```xml
<bean id="reporter" class="example.Reporter">
    <constructor-arg index="0" ref="service"/>
    <constructor-arg index="1" value="DEBUG:"/>
</bean>
```

to the `c`-namespace.

**Answer:**

```xml
<bean id="reporter"
      class="example.Reporter"
      c:_0-ref="service"
      c:_1="DEBUG:"/>
```

Remember to declare `xmlns:c="http://www.springframework.org/schema/c"` on the `<beans>` root.

### Exercise 6 — Bean Name vs. Parameter Name

`<bean id="retry" ...><constructor-arg name="limit" value="3"/></bean>`. What roles do the two strings `retry` and `limit` play?

**Answer:** `retry` is the bean name in Spring; `limit` is the Java constructor parameter name. The bean name is not used to infer parameter index.

### Exercise 7 — Inner Bean or Shared Bean?

Two services need the same `FilterPolicy` singleton. Should you duplicate two inner `<bean>` definitions or define one named bean?

**Answer:** Define one named bean `filterPolicy` and use `<constructor-arg ref="filterPolicy"/>` in both services. An inner bean belongs privately to its outer bean and does not provide shared container singleton identity like a named singleton.

### Exercise 8 — Static Factory

A class `ClientFactory` has `public static Client build(String url)`. Can XML pass the argument using `<constructor-arg>`?

**Answer:** Yes, when the bean is declared with `class="...ClientFactory" factory-method="build"`; the argument is passed to the **factory method**, not `ClientFactory`'s constructor.

### Exercise 9 — Prototype

A singleton `Scheduler` receives a prototype `Worker` in its constructor. Does `Scheduler` automatically receive a new worker on every `run()` call?

**Answer:** No. The prototype is resolved when the singleton constructor runs; `Scheduler` retains that reference. To get a new worker per job, use an appropriate dynamic lookup/factory.

### Exercise 10 — Placeholder

Does `<constructor-arg value="${service.timeout}"/>` automatically read the key from `app.properties`?

**Answer:** No. Placeholder/environment configuration infrastructure is required, such as a property-placeholder processor or equivalent configuration. After resolution, Spring can convert the string to the constructor parameter type.

### Exercise 11 — Constructor Cycle

`A(B)` and `B(A)` are wired via `ref`. Can reordering `<bean>` tags fix it?

**Answer:** No. The dependency graph contains a cycle; you must change responsibilities/abstractions or orchestration rather than just reordering XML.

### Exercise 12 — Predict Output

In the Section 13 project, what do `service.describe("BK-7")` and `reporter.line("MUG-2")` return?

**Answer:** `SKU-Java book` and `REPORT:SKU-Coffee mug`. Prefix `SKU-` comes from `<constructor-arg index="1" value="SKU-"/>`, and `REPORT:` comes from `c:_1="REPORT:"`.

### Exercise 13 — Changing Java Signature

You change `Reporter(CatalogService service, String label)` to `Reporter(String label, CatalogService service)` while keeping `c:_0-ref` and `c:_1`. Is this safe?

**Answer:** No. Positional mapping now swaps types: `c:_0-ref` feeds the service into the `String` parameter and `c:_1` feeds the literal string into the `CatalogService` parameter. Update the XML or use name-based mapping with corresponding metadata.

### Exercise 14 — Refactoring XML to Java Config

XML:

```xml
<bean id="catalogService" class="example.CatalogService">
    <constructor-arg ref="catalog"/>
    <constructor-arg value="SKU-"/>
</bean>
```

Write the equivalent Java factory wiring.

**Answer:**

```java
@Bean("catalogService")
CatalogService catalogService(Catalog catalog) {
    return new CatalogService(catalog, "SKU-");
}
```

Ensure the Java config is registered with Spring and remove the duplicate XML definition when migrating.

## 26. Pre-Merge Checklist for XML Configuration

- [ ] XML `<beans>` root, namespaces/schema, and resource path are valid.
- [ ] Bean class exists and has a suitable constructor or factory method.
- [ ] Every required dependency is expressed via `ref` or an appropriate explicit `value`.
- [ ] `ref` is not confused with literal `value`.
- [ ] `index` (if used) starts at 0 and matches the Java parameter order.
- [ ] `type` is explicit enough when overloads or multiple primitive/string values exist.
- [ ] `name` has Java parameter-name metadata via `-parameters` or `@ConstructorProperties`.
- [ ] No duplicate `index`/`name` or omitted arguments.
- [ ] Multiple `String` parameters are semantically disambiguated.
- [ ] Type conversion of literal values is tested in an `ApplicationContext`.
- [ ] `c:` namespace is declared properly; the `-ref` suffix is understood.
- [ ] Collections/inner beans are used only when ownership/lifecycle matches.
- [ ] Constructor autowiring has a unique candidate or explicit qualifier.
- [ ] No constructor cycles in the dependency graph.
- [ ] Singleton/prototype scopes match how consumers retain references.
- [ ] No second Spring context is created just to fetch a dependency.
- [ ] When migrating XML to `@Bean`, bean names and dependency semantics are preserved.
- [ ] Integration tests verify managed identity, arguments, and output.
- [ ] Context is closed to clean up resources per lifecycle rules.

## Summary

`<constructor-arg>` is central to **constructor-based dependency injection in Spring XML**. It explicitly describes a bean's required dependencies without requiring Java classes to instantiate collaborators themselves.

The three key disambiguation attributes are:

- **`index`:** **0-based** argument position, requiring no parameter-name metadata.
- **`type`:** helps Spring find the right signature, especially with literals and overloaded constructors.
- **`name`:** makes XML describe parameter meaning; requires `-parameters` or `@ConstructorProperties` so Spring recognizes names reliably.

And the two fundamental value forms:

- **`ref`:** retrieves a **managed bean reference**.
- **`value`:** passes a **literal**, converted to the target parameter type.

You can use the **`c:` namespace** as a shorthand, nested `<list>`/`<map>` for complex structures, and `<constructor-arg>` also applies to factory method arguments. Whichever form you choose, prioritize **clear constructor signatures, acyclic dependency graphs, proper scopes/lifecycle, and integration tests**. XML should highlight dependency relationships rather than obscure them behind overloads or unpredictable conversions.

## Official References

- [Spring Framework 6.2 — Dependency Injection](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-collaborators.html): constructor-based DI, argument type/index/name matching, `-parameters`, and `@ConstructorProperties`.
- [Spring Framework 6.2 — Dependencies and Configuration in Detail](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-properties-detailed.html): `ref`, `value`, `idref`, inner beans, collections, and the c-namespace.
- [Spring Framework 6.2 — Autowiring Collaborators](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-autowire.html): `autowire="constructor"`, limits, and ambiguity.
- [Spring Framework 6.2 — Bean Definition Basics](https://docs.spring.io/spring-framework/reference/6.2/core/beans/basics.html): bean definitions, XML configuration, and the container.
- [Spring Framework 6.2 — Bean Scopes](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html): singleton, prototype, and lifetime semantics.
- [Spring Framework 6.2 — Composing Java-based Configurations](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html): combining XML with `@ImportResource`.
