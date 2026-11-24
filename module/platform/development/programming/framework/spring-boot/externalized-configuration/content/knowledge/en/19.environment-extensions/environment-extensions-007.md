# Registering `EnvironmentPostProcessor` and Coordinating Execution Order in Spring Boot 3.3

## 1. Problem: Needing to Modify Environment Before Creating Beans

In a Spring Boot application, configuration values can come from `application.properties`, `application.yaml`, environment variables, command-line arguments, Java system properties, external files, and many other sources. Spring Boot combines these sources into `Environment`, after which components use `@Value`, `Environment`, or `@ConfigurationProperties` to read and bind values.

Some requirements go beyond merely declaring a file:

- Adding a `PropertySource` that supplies **default values of an internal library**.
- Reading a configuration file by custom convention from the classpath and placing keys into `Environment`.
- Creating a derived value from existing properties before business beans initialize.
- Migrating an old configuration key name to a new name during a transition period.
- Adding or modifying the environment early enough for the startup system to read required keys.
- Coordinating multiple environment-processing steps in an intentional order.

Spring Boot 3.3 provides the **`EnvironmentPostProcessor`** interface for this purpose.

This lesson belongs to the **Environment Extensions** group of **Spring Boot Externalized Configuration**. It focuses on **how to register `EnvironmentPostProcessor` and coordinate execution order**, not just writing a single Java class.

You will practice:

1. Writing an `EnvironmentPostProcessor` using `MapPropertySource`.
2. Registering it in `META-INF/spring.factories` with the exact full key.
3. Coordinating two processors using `Ordered` and `ConfigDataEnvironmentPostProcessor.ORDER`.
4. Distinguishing **processor execution order** from **`PropertySource` precedence**.
5. Observing values in `ApplicationRunner` and testing overrides from the CLI.
6. Understanding `@Order`, early logging, and `DeferredLogFactory`.
7. Avoiding registration bugs, overly early bean dependencies, accidental source overrides, and duplicate processing.
8. Writing unit tests for order/`PropertySource` and integration tests for discovery.

Examples target **Java 17+ and Spring Boot 3.3.x**.

## 2. What Is `EnvironmentPostProcessor`?

Official interface:

```java
package org.springframework.boot.env;

public interface EnvironmentPostProcessor {

    void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application);
}
```

Two parameters:

- `ConfigurableEnvironment`: mutable configuration environment; from it you access `MutablePropertySources`, profiles, and property values.
- `SpringApplication`: the starting Spring Boot application, not a finalized `ApplicationContext`.

According to the Spring Boot 3.3 JavaDoc, `EnvironmentPostProcessor` allows customizing `Environment` **before the application context is refreshed**.

One way to picture it:

```text
SpringApplication.run(...)
         |
         v
Environment is prepared
         |
         +-- Boot EnvironmentPostProcessors
         +-- Custom EnvironmentPostProcessors
         |       |
         |       +-- add / modify PropertySources
         |       +-- process supplementary config data
         |
         v
Environment has been adjusted
         |
         v
ApplicationContext created and refreshed
         |
         +-- Conditions / auto-configuration
         +-- @ConfigurationProperties binding
         +-- @Value / Environment lookup
         +-- Bean initialization
         |
         v
Application serves requests
```

Difference from `@PostConstruct` or `ApplicationRunner`: those mechanisms run when beans/context are already created or the application is nearly ready, too late for many startup configuration decisions.

### 2.1. What Is `Environment`?

`Environment` is more than `System.getenv()`. It abstracts multiple sources with **varying priorities** and provides APIs such as:

```java
environment.getProperty("demo.region")
environment.getProperty("demo.timeout", Duration.class)
environment.getActiveProfiles()
```

When modifying the source collection, use:

```java
MutablePropertySources sources = environment.getPropertySources();
```

with `ConfigurableEnvironment`.

A `PropertySource` represents a named source, such as command-line arguments, system properties, system environment, or a `Map` structure built by the application.

### 2.2. `EnvironmentPostProcessor` Differs from `BeanFactoryPostProcessor`

These two types serve two phases and two purposes:

| Tool | Primary Target |
| --- | --- |
| `EnvironmentPostProcessor` | Modifies `Environment` in Spring Boot's early phase |
| `ApplicationContextInitializer` | Customizes `ApplicationContext` before refresh |
| `BeanFactoryPostProcessor` | Affects bean definitions/BeanFactory during context preparation |
| `BeanPostProcessor` | Intercepts individual bean lifecycles |
| `ApplicationRunner` | Runs after application context startup |
| `@PropertySource` | Loads a `PropertySource` via Spring configuration, usually later than when Boot needs certain startup keys |

Because these extensions live at different layers, **`EnvironmentPostProcessor` execution order does not automatically coordinate bean post-processors**.

## 3. Where Does Spring Boot Discover `EnvironmentPostProcessor`?

In **Spring Boot 3.3**, the standard registration method is declaring the implementation in:

```text
src/main/resources/META-INF/spring.factories
```

Contents for one processor:

```properties
org.springframework.boot.env.EnvironmentPostProcessor=example.environment.MyEnvironmentPostProcessor
```

The left side is the **fully qualified interface name** `org.springframework.boot.env.EnvironmentPostProcessor`, not the application's class name, not a Spring Framework `spring.factories` namespace, and not an arbitrary name.

The right side is the fully qualified name of the Java implementation, including package and class.

Once `spring.factories` is on the classpath, Spring Boot uses its factory loading mechanism to locate and instantiate the registered processors.

**Point to remember:** merely writing a class with `implements EnvironmentPostProcessor` is **not enough** for Boot to auto-discover it. Nor is `@Component` a standard replacement for `EnvironmentPostProcessor` registration.

### 3.1. Do Not Confuse with `AutoConfiguration.imports`

Since Spring Boot 3, auto-configuration classes are typically published via:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

However, **`EnvironmentPostProcessor` still uses**:

```text
META-INF/spring.factories
```

These are two discovery mechanisms for **two different kinds of extensions**. Do not copy the processor name into `AutoConfiguration.imports` expecting `postProcessEnvironment(...)` to run automatically.

### 3.2. Registering Multiple Processors

A `spring.factories` file can declare a list:

```properties
org.springframework.boot.env.EnvironmentPostProcessor=example.environment.DefaultsEnvironmentPostProcessor,example.environment.DerivedEnvironmentPostProcessor
```

This is a single line in the `.properties` file. You can use `\` line continuation per properties syntax if the list is long.

**The order of appearance in the list should not be the execution order contract.** To coordinate execution order, use `Ordered` or `@Order` on the classes.

### 3.3. If the Project Already Has `spring.factories`

Do not create multiple definitions for the same key in **the same file** and rely on the parser merging them. Use a single value containing comma-separated class names; keep other registrations under different keys in that file intact.

For libraries packaged across multiple JARs, each JAR can carry its own `META-INF/spring.factories`. The factory loading mechanism can load registrations from the classpath without requiring everything to be combined into the application's own file.

## 4. How Is `EnvironmentPostProcessor` Instantiated?

For a simple implementation:

```java
package example.environment;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;

public final class MyEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application
    ) {
        // Modify Environment here.
    }
}
```

Spring Boot instantiates the processor early, before regular beans are created. This has consequences:

- Do not assume the processor's constructor can inject `@Service`, `@Repository`, `DataSource`, HTTP clients, or application beans.
- Do not expect `@Value` on processor fields to be processed as on a normal Spring bean.
- Do not put `@PostConstruct` on a processor expecting it to act as an early hook.
- Use the `ConfigurableEnvironment` parameter to retrieve configuration already present when the processor runs.
- If you need special Boot-supported APIs in the constructor, use only the constructor parameter types permitted by JavaDoc.

Spring Boot 3.3 supports **optional** constructor parameters for processors:

- `DeferredLogFactory`.
- `ConfigurableBootstrapContext`; related bootstrap APIs such as `BootstrapContext` or `BootstrapRegistry` are documented.

Example:

```java
public MyEnvironmentPostProcessor(DeferredLogFactory factory) {
    // Create a logger supporting deferred logging.
}
```

Do not assume an arbitrary constructor taking `MyRepository` will be autowired like a Spring bean. This factory loading mechanism does not carry `ApplicationContext`'s DI contract.

## 5. Two Types of Ordering That Are Easily Confused

This is the most important point of the lesson.

### 5.1. Processor Execution Order

Suppose there are two processors:

```text
A: loads fallback values
B: reads fallbacks and creates a derived value
```

If B must see data added by A, ensure **A runs before B**:

```text
Environment before A
       |
       v
A adds PropertySource "defaults"
       |
       v
Environment after A
       |
       v
B reads newly added keys, creates "derived"
       |
       v
Environment after B
```

This is **processor execution order**.

### 5.2. PropertySource Precedence

An `Environment` holds multiple `PropertySource` instances:

```text
PropertySources (described from highest to lowest priority)
  - commandLineArgs
  - systemProperties
  - systemEnvironment
  - config data
  - defaults
```

When the same key exists in multiple sources, the source found first in precedence order normally wins.

```java
sources.addFirst(mySource);
```

places the source at the front of the source list at the moment of the call, so it can **override** existing sources.

```java
sources.addLast(mySource);
```

places the source at the end of the current list, so it normally acts only as a **fallback** relative to existing sources.

This is **`PropertySource` precedence**.

**A running before B does not mean A's values always outrank B.** B can add a `PropertySource` at the end of the list, or A can add a source at the front. Decisions must account for **both ordering axes**.

### 5.3. Comparison Table

| Question | Relevant Mechanism |
| --- | --- |
| Which processor runs first? | `Ordered#getOrder()`, `@Order` |
| Can one processor see sources added by another processor yet? | Execution order |
| If multiple sources contain `demo.mode`, which value wins? | `PropertySource` order |
| Were `application.yaml` values loaded before the processor read them? | Processor timing relative to Config Data |
| Was profile-specific config processed yet? | Config Data processing timing |
| Does a CLI override beat fallback values? | `addFirst`/`addLast` placement and effective sources |
| Should multiple threads be spawned to run processors? | No; follow official lifecycle and ordering contracts |

## 6. Coordinating Processors with `Ordered`

Spring Boot 3.3 allows `EnvironmentPostProcessor` implementations to implement:

```java
import org.springframework.core.Ordered;
```

Example:

```java
public final class AlphaEnvironmentPostProcessor
        implements EnvironmentPostProcessor, Ordered {

    @Override
    public int getOrder() {
        return 100;
    }

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application
    ) {
        // ...
    }
}
```

`Ordered` declares:

```java
int getOrder();
```

General rule:

**Lower order values have higher execution priority.**

Example:

```text
order=10    -> runs earlier
order=50    -> runs later
order=100   -> runs even later
```

The constants:

```java
Ordered.HIGHEST_PRECEDENCE
Ordered.LOWEST_PRECEDENCE
```

represent the two ends of the order range.

### 6.1. Do Not Use Arbitrary Integers When Depending on Config Data

If the requirement is "run after Boot has read `application.yaml`", the integer `100` does not express that intent clearly. Spring Boot has an internal processor:

```java
org.springframework.boot.context.config.ConfigDataEnvironmentPostProcessor
```

This class implements `Ordered` and exposes the constant:

```java
ConfigDataEnvironmentPostProcessor.ORDER
```

Thus you can write:

```java
@Override
public int getOrder() {
    return ConfigDataEnvironmentPostProcessor.ORDER + 1;
}
```

to express that the custom processor runs after the Config Data processor under `EnvironmentPostProcessor` ordering.

If you want to run **before** Config Data:

```java
@Override
public int getOrder() {
    return ConfigDataEnvironmentPostProcessor.ORDER - 1;
}
```

Choosing before/after must be based on the data the processor needs. There is no rule saying "custom processors must always run first to have high priority".

### 6.2. What Does Running Before Config Data Mean?

At that moment, the processor must not assume `application.yaml` and `application-{profile}.yaml` have been loaded by Config Data. It can work with very early sources such as system properties, environment variables, or sources already present when invoked.

If a processor needs to fetch `demo.region` declared **only in `application.yaml`**, pick an order after Config Data so it can read it.

If the goal is supplying a property Boot must read when **initializing Config Data**, it must run early enough and carefully respect `spring.config.*` compatibility; customizing bootstrap keys can change the entire config-loading behavior.

### 6.3. Do Not Hardcode Boot's Internal Numeric Values When a Constant Exists

Avoid writing:

```java
return -2147483638;
```

just because it currently happens to match an internal order you read in one version's source code. Using:

```java
return ConfigDataEnvironmentPostProcessor.ORDER + 1;
```

expresses intent far better and reduces coupling to an implementation-detail number.

## 7. Coordinating with `@Order`

JavaDoc also permits using:

```java
import org.springframework.core.annotation.Order;
```

Example:

```java
@Order(200)
public final class BetaEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application
    ) {
        // ...
    }
}
```

Likewise, lower values are sorted earlier.

Choosing between the two approaches:

| Approach | Advantage |
| --- | --- |
| `implements Ordered` | `getOrder()` can express order in Java code; easy to reference Boot constants |
| `@Order(...)` | Concise syntax when the order is a suitable compile-time constant |
| No explicit order | Less code, but should not be used when ordering dependencies exist |

Within a single processor, stick to **one primary convention** for clarity. If both `Ordered` and `@Order` appear with conflicting values, readers would have to know comparator details to see which takes precedence.

### When Two Processors Have the Same Order

Do not rely on `spring.factories` listing A before B or on stable classpath ordering to assume A will definitely run before B if they share the same order.

If B depends on A's data, assign **distinct and explicit orders**, for example:

```text
A = ConfigDataEnvironmentPostProcessor.ORDER + 1
B = ConfigDataEnvironmentPostProcessor.ORDER + 20
```

Equal orders are not a reliable dependency contract between processors.

## 8. Complete Example — Two Processors with an Ordering Relationship

Suppose an application needs:

- `demo.region` taken from `application.properties`.
- `demo.mode` potentially supplied by file or CLI.
- Fallbacks `demo.mode=development` and `demo.retry-count=2` if no other source provides them.
- `demo.instance-label` as a derived string `region/mode`.
- If the user explicitly configured `demo.instance-label`, that value must take priority over the derived value.

Design:

```text
ConfigDataEnvironmentPostProcessor
     |
     v
DefaultsEnvironmentPostProcessor
  ORDER = ConfigDataEnvironmentPostProcessor.ORDER + 1
  addLast(demo.mode, demo.retry-count)
     |
     v
DerivedEnvironmentPostProcessor
  ORDER = ConfigDataEnvironmentPostProcessor.ORDER + 20
  reads demo.region, demo.mode
  addLast(demo.instance-label)
     |
     v
Application beans use the prepared Environment
```

This example **intentionally uses `addLast`** so it does not accidentally override values provided by deployers.

### 8.1. Directory Structure

```text
src/
  main/
    java/
      example/
        environment/
          EnvironmentDemoApplication.java
          DefaultsEnvironmentPostProcessor.java
          DerivedEnvironmentPostProcessor.java
    resources/
      application.properties
      META-INF/
        spring.factories
```

### 8.2. Processor A: Loading Fallbacks

Create:

`src/main/java/example/environment/DefaultsEnvironmentPostProcessor.java`

```java
package example.environment;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.config.ConfigDataEnvironmentPostProcessor;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.Ordered;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.MutablePropertySources;

public final class DefaultsEnvironmentPostProcessor
        implements EnvironmentPostProcessor, Ordered {

    public static final String SOURCE_NAME = "demo-epp-defaults";

    @Override
    public int getOrder() {
        return ConfigDataEnvironmentPostProcessor.ORDER + 1;
    }

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application
    ) {
        MutablePropertySources sources = environment.getPropertySources();

        if (sources.contains(SOURCE_NAME)) {
            return;
        }

        Map<String, Object> defaults = Map.of(
                "demo.mode", "development",
                "demo.retry-count", "2"
        );

        sources.addLast(new MapPropertySource(SOURCE_NAME, defaults));
    }
}
```

Explanation:

- The processor executes after Config Data according to its declared order.
- The source has a fixed name `demo-epp-defaults`, convenient for identification in diagnostics.
- `MapPropertySource` turns key/value pairs into a configuration source.
- `addLast` prioritizes existing sources ahead of the fallbacks.
- The `contains(SOURCE_NAME)` guard reduces the risk of adding the same source twice if the processor is invoked again in tests or special contexts.
- Fallbacks are not a `@ConfigurationProperties` bean; beans can bind values from the newly added source when initialized later.

The data in `Map` consists of non-sensitive example values. Do not put tokens, passwords, or private keys directly into source code.

### 8.3. Processor B: Creating a Derived Value

Create:

`src/main/java/example/environment/DerivedEnvironmentPostProcessor.java`

```java
package example.environment;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.config.ConfigDataEnvironmentPostProcessor;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.Ordered;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.MutablePropertySources;
import org.springframework.util.StringUtils;

public final class DerivedEnvironmentPostProcessor
        implements EnvironmentPostProcessor, Ordered {

    public static final String SOURCE_NAME = "demo-epp-derived";

    @Override
    public int getOrder() {
        return ConfigDataEnvironmentPostProcessor.ORDER + 20;
    }

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application
    ) {
        MutablePropertySources sources = environment.getPropertySources();

        if (sources.contains(SOURCE_NAME)) {
            return;
        }

        String region = environment.getProperty("demo.region");

        if (!StringUtils.hasText(region)) {
            return;
        }

        String mode = environment.getProperty(
                "demo.mode", "development");

        String label = region + "/" + mode;

        sources.addLast(new MapPropertySource(
                SOURCE_NAME,
                Map.of("demo.instance-label", label)
        ));
    }
}
```

Analysis:

1. `DerivedEnvironmentPostProcessor` runs **after** `DefaultsEnvironmentPostProcessor`.
2. It reads `demo.region`, which may come from `application.properties`, profiles, CLI, or another source.
3. It reads `demo.mode`; if the file did not declare mode, it can see processor A's fallback.
4. It builds the string `region/mode`.
5. `addLast` places the derived value at fallback priority. Deployers can still directly declare `demo.instance-label` in a higher-priority source.

If `demo.region` is missing or blank, this example **does not create** `demo.instance-label`. That is an illustrative choice; real applications must decide which properties are mandatory and how validation should handle missing values.

### 8.4. Registering in `spring.factories`

Create the **exact** file:

`src/main/resources/META-INF/spring.factories`

Contents:

```properties
org.springframework.boot.env.EnvironmentPostProcessor=example.environment.DefaultsEnvironmentPostProcessor,example.environment.DerivedEnvironmentPostProcessor
```

Notes:

- Key is `org.springframework.boot.env.EnvironmentPostProcessor`.
- Class names include the full `example.environment` package.
- Do not add `@Component`.
- Do not write to `AutoConfiguration.imports`.
- Do not use an arbitrary separator like `;` when the factory format requires a comma-separated list.
- Listing order on the line is merely registration order; **execution order is decided by `getOrder()`**.

### 8.5. Source Config File

Create:

`src/main/resources/application.properties`

```properties
spring.application.name=epp-order-demo

demo.region=ap-southeast-1
demo.mode=production
```

Here `demo.retry-count` and `demo.instance-label` do not appear in the file:

- `demo.retry-count` will receive fallback `2`.
- `demo.instance-label` can be generated by processor B.
- `demo.mode` comes from the file as `production`, beating fallback `development` because the fallback source was added with `addLast`.

### 8.6. Application Reading Results

Create:

`src/main/java/example/environment/EnvironmentDemoApplication.java`

```java
package example.environment;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class EnvironmentDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                EnvironmentDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner display(Environment environment) {
        return args -> {
            System.out.println("demo.region="
                    + environment.getProperty("demo.region"));

            System.out.println("demo.mode="
                    + environment.getProperty("demo.mode"));

            System.out.println("demo.retry-count="
                    + environment.getProperty("demo.retry-count"));

            System.out.println("demo.instance-label="
                    + environment.getProperty("demo.instance-label"));
        };
    }
}
```

`ApplicationRunner` runs after the context has initialized. Therefore it is suitable for **observing output**, not for registering or running `EnvironmentPostProcessor`.

### 8.7. Expected Output

After running with the Maven wrapper:

```bash
./mvnw spring-boot:run
```

or the packaged JAR:

```bash
java -jar app.jar
```

(replace `app.jar` with the actual filename), the illustrative output lines are:

```text
demo.region=ap-southeast-1
demo.mode=production
demo.retry-count=2
demo.instance-label=ap-southeast-1/production
```

The data is produced as follows:

| Key | Effective Source in Example |
| --- | --- |
| `demo.region` | `application.properties` |
| `demo.mode` | `application.properties`, beats fallback |
| `demo.retry-count` | `demo-epp-defaults` |
| `demo.instance-label` | `demo-epp-derived` |

If you do not see these lines, check `spring.factories`, classpath, package, build output, and any higher-priority configuration sources.

## 9. Experiments: Changing One Source at a Time to Understand Ordering

### Experiment A: CLI Overrides `demo.mode`

Run:

```bash
java -jar app.jar --demo.mode=canary
```

Assuming no other special priority sources:

```text
demo.region=ap-southeast-1
demo.mode=canary
demo.retry-count=2
demo.instance-label=ap-southeast-1/canary
```

Because processor B runs after Config Data and reads `Environment` at that time, it sees the CLI value `canary`.

### Experiment B: CLI Overrides the Derived Key Itself

```bash
java -jar app.jar --demo.instance-label=operator-defined
```

Final value result:

```text
demo.instance-label=operator-defined
```

Processor B may still create a fallback `ap-southeast-1/production`, yet `addLast` preserves priority for the operator's configuration.

### Experiment C: Removing `demo.mode` from the File

If `application.properties` only contains:

```properties
demo.region=ap-southeast-1
```

then:

```text
demo.mode=development
demo.retry-count=2
demo.instance-label=ap-southeast-1/development
```

The fallback from processor A takes effect before processor B reads `demo.mode`.

### Experiment D: Removing `demo.region`

If no source provides `demo.region`, processor B does not create `demo.instance-label`. The output may be:

```text
demo.region=null
demo.instance-label=null
```

The word `"null"` in output comes from Java `String` concatenation with a `null` result; it does not mean `Environment` stored the string `"null"` as a property.

In a real project, if `demo.region` is mandatory, use `@ConfigurationProperties` and validation to fail fast or report a meaningful error rather than printing null.

## 10. What Changes If `addLast` Is Replaced by `addFirst`?

In processor A:

```java
sources.addLast(new MapPropertySource(...));
```

means the fallback source is appended to the end of existing priority order.

If replaced with:

```java
sources.addFirst(new MapPropertySource(...));
```

the `demo-epp-defaults` source can beat values for the same keys in existing sources, including `application.properties` or CLI at the time of insertion.

For instance, with fallback:

```text
demo.mode=development
```

using `addFirst` could make the operator see `demo.mode=development` even though they declared `demo.mode=production` in the file.

This is generally **unsuitable for defaults**. However, `addFirst` can be useful when there is a forced-value policy, provided it is clearly designed and documented.

### 10.1. `addBefore` and `addAfter`

`MutablePropertySources` also supports:

```java
sources.addBefore(existingSourceName, customSource);
sources.addAfter(existingSourceName, customSource);
```

These two methods position a source relative to an **existing** source.

Condition: `existingSourceName` must be present at execution time. Framework-added source names can vary by version, profile, and loading mechanism. Do not hardcode an internal name prone to change without good reason and tests.

### 10.2. `replace` and `remove`

You can call:

```java
sources.replace(name, newSource);
sources.remove(name);
```

However, these two operations are invasive. Replacing/removing a source belonging to Boot or another library can broadly alter configuration behavior. For this lesson, **adding a source with its own dedicated name** is safer and easier to diagnose.

### 10.3. Do Not Conflate Three Concepts

| Concept | Example | Meaning |
| --- | --- | --- |
| Processor order | `getOrder() = ... + 20` | Processor runs after processors with lower order |
| Source position | `sources.addLast(...)` | New source's values act as fallbacks at insertion time |
| Final winning source | `environment.getProperty("demo.mode")` | Result after evaluating all current PropertySources |

A processor running late does not automatically override old sources. Conversely, a processor running early that adds a source with `addFirst` can strongly affect processors running afterward.

## 11. Why Is Order Relative to `ConfigDataEnvironmentPostProcessor` Especially Important?

`ConfigDataEnvironmentPostProcessor` is the Boot component responsible for loading/applying Config Data into Spring `Environment`. Those sources include `application.properties`, YAML, profile-specific documents, and supported config data imports.

If your processor needs:

```java
String region = environment.getProperty("demo.region");
```

and `demo.region` **exists only in `application.properties`**, you want Config Data applied first.

That is why the example uses:

```java
ConfigDataEnvironmentPostProcessor.ORDER + 1
```

and:

```java
ConfigDataEnvironmentPostProcessor.ORDER + 20
```

### 11.1. Running Before Config Data

A processor with order:

```java
ConfigDataEnvironmentPostProcessor.ORDER - 1
```

is normally invoked before the Config Data processor, so it cannot assume configuration from `application.yaml` is already available.

If you must supply a value that Config Data needs to read very early, you can design a processor before Config Data, but you must understand exactly which sources are already available and the Boot rules that apply.

For example, properties such as:

```text
spring.config.name
spring.config.location
spring.config.additional-location
```

are used early to determine config loading locations. Modifying these values with a processor requires care to avoid circular dependencies and inconsistent startup behavior.

### 11.2. Running After Config Data

A processor running after Config Data can:

- Read values already loaded from `application.properties`/YAML.
- Read active profiles determined during config data processing.
- Generate fallbacks for application business keys.
- Compute derived values from effective sources.

However, if you add a property that Boot **already consumed earlier to decide config data**, do not assume Boot will go back and re-run the entire load from scratch. Adding a late `PropertySource` does not re-trigger the bootstrap mechanism.

### 11.3. Avoid "Manually Re-Invoking" the Config Data Processor

Do not arbitrarily instantiate:

```java
new ConfigDataEnvironmentPostProcessor(...)
```

or call `applyTo` repeatedly from your processor just to make sure config data is loaded. Use **order** to coordinate and let Spring Boot manage the standard lifecycle.

## 12. Ordering Across Library Processors

In a large application, multiple dependencies may ship EPPs:

```text
spring-boot core
internal-security-starter
internal-observability-starter
application-specific extension
```

Suppose:

- A adds default fallbacks.
- B decrypts a custom-formatted source.
- C creates derived properties depending on B's output.

The design must clarify:

```text
B must run before C
Does A need to run before B?
Which keys does C read?
Does B add its source at the front or end?
```

One approach:

```java
public final class SecurityEnvironmentPostProcessor
        implements EnvironmentPostProcessor, Ordered {
    @Override
    public int getOrder() {
        return ConfigDataEnvironmentPostProcessor.ORDER + 5;
    }
}
```

```java
public final class DerivedEnvironmentPostProcessor
        implements EnvironmentPostProcessor, Ordered {
    @Override
    public int getOrder() {
        return ConfigDataEnvironmentPostProcessor.ORDER + 10;
    }
}
```

This is a **local coordination example**. If multiple teams share that order range, agree on conventions in library documentation rather than letting each module pick random numbers.

When complex dependency requirements cannot be expressed clearly through simple ordering, consider consolidating the dependent steps into a single processor with clear internal methods rather than building a chain of dozens of numerically coupled EPPs.

## 13. Do Not Confuse `@Order` with Class Name Order in `spring.factories`

A file:

```properties
org.springframework.boot.env.EnvironmentPostProcessor=example.environment.DerivedEnvironmentPostProcessor,example.environment.DefaultsEnvironmentPostProcessor
```

lists B before A.

If A's `getOrder()` is smaller than B's, the EPP system still uses order metadata to sort per contract. Therefore, do not edit the class list just to try to control execution order.

To express the requirement:

```text
A runs before B
```

use:

```text
A.getOrder() < B.getOrder()
```

while choosing `getOrder()` for both so they sit appropriately relative to Config Data.

When orders are equal, avoid relying on classpath order or how the factory loader lists classes as a long-term guarantee.

## 14. Early Logging: Why Normal `Logger`s May Not Behave as Expected

`EnvironmentPostProcessor` runs before the entire application and logging configuration are finalized. Spring Boot 3.3 API docs allow processors to accept `DeferredLogFactory` via constructor.

Example:

```java
package example.environment;

import org.apache.commons.logging.Log;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.boot.logging.DeferredLogFactory;
import org.springframework.core.env.ConfigurableEnvironment;

public final class LoggingEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    private final Log log;

    public LoggingEnvironmentPostProcessor(
            DeferredLogFactory logFactory
    ) {
        this.log = logFactory.getLog(getClass());
    }

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application
    ) {
        this.log.info("Preparing custom environment properties");
    }
}
```

This is a standalone **logging** example, not a third class to add to `spring.factories` in the two-processor demo unless you intentionally register it.

Benefit: log output can be deferred until the application's logging configuration is more fully prepared.

**Do not log secret data** or dump the entire `Environment`. Some property sources may hold passwords, tokens, or connection strings. Even deferred logging does not automatically make sensitive content safe.

### 14.1. Why Not Inject a Logger Service?

An application-specific logging service may not yet exist during the EPP phase. Use Boot-supported early logging or log carefully; do not pull the entire Spring context dependency graph into an EPP constructor.

## 15. What Role Does `ConfigurableBootstrapContext` Play?

Spring Boot 3.3 allows an EPP to accept `ConfigurableBootstrapContext` in its constructor. This is an early collaboration area for components needing to share objects or results created before the application context is complete.

Idea:

```text
Bootstrap phase
    |
    +-- Processor creates a shared object
    +-- BootstrapContext can hold the object
    |
    v
ApplicationContext preparation phase
    |
    +-- Supporting components can use the registered info
```

Do not mistake bootstrap context for a full `ApplicationContext` where you can arbitrarily look up any bean. It has its own API and purpose.

For adding a `MapPropertySource`, `ConfigurableBootstrapContext` is **not needed**. When expensive loading or data sharing across startup steps is required, consult the docs and design explicit lifecycles rather than creating a global mutable singleton.

## 16. Idempotence: Avoiding Unwanted Effects on Re-Execution

In our example, each processor has:

```java
if (sources.contains(SOURCE_NAME)) {
    return;
}
```

This helps when:

- Unit tests invoke the processor multiple times.
- A test harness prepares contexts multiple times and wants to preserve a single source.
- An extension is intentionally re-invoked.

However, a "skip if present" guard does not suit every requirement. If the right rule is **updating** values from a new environment, you may need to recompute and replace the source under controlled logic.

Do not call:

```java
sources.addFirst(new MapPropertySource("same-name", map));
```

repeatedly assuming source structure remains stable. `MutablePropertySources` manages sources by name, and adding duplicate names can unintentionally shift position/order.

Better:

1. Pick a stable source name with its own prefix.
2. Decide upfront on an **add once**, **replace**, or **merge** policy.
3. Check source presence before operating.
4. Do not remove/replace another module's source without a contract.
5. Verify with a double-invocation test.

## 17. Do Not Turn EPP into a Place for Network or Database Calls

An error-prone approach:

```java
public MyEnvironmentPostProcessor(RemoteSettingsClient client) {
    this.client = client;
}
```

Do not expect `RemoteSettingsClient` to be a ready Spring bean. Moreover, making network calls during bootstrap carries risks:

- Without timeouts, the application can hang at startup.
- A transient endpoint failure prevents the entire app from booting.
- Logging/metrics/tracing are not yet fully ready.
- Circular dependency between config and the client using that config.
- Credentials may not yet be fully loaded.
- Integration tests become tied to external environments.

If the task is loading a **standard remote configuration source**, Spring Boot has the **Config Data API**, including `ConfigDataLocationResolver` and `ConfigDataLoader` for custom location types.

Consider that dedicated API when integrating a location like `custom://...` into `spring.config.import`, rather than trying to emulate all profile, import, optional, and precedence mechanics inside an EPP.

EPP fits best when modifying the environment with clear rules, early enough, with minimal dependencies and deterministic startup behavior.

## 18. Adding a Custom YAML File via EPP

Besides `MapPropertySource`, an EPP can read a file and add a `PropertySource`.

Mental model:

```text
classpath:/feature-defaults.yaml
         |
         v
YamlPropertySourceLoader
         |
         v
PropertySource(s)
         |
         v
environment.getPropertySources().addLast(...)
```

Spring Boot provides:

```java
org.springframework.boot.env.YamlPropertySourceLoader
```

for loading YAML from a `Resource`.

An illustration loading an optional file:

```java
package example.environment;

import java.io.IOException;
import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.boot.env.YamlPropertySourceLoader;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;
import org.springframework.core.io.ClassPathResource;

public final class FeatureDefaultsPostProcessor
        implements EnvironmentPostProcessor {

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application
    ) {
        var resource = new ClassPathResource("feature-defaults.yaml");

        if (!resource.exists()) {
            return;
        }

        try {
            List<PropertySource<?>> sources =
                    new YamlPropertySourceLoader()
                            .load("feature-defaults", resource);

            for (PropertySource<?> source : sources) {
                if (!environment.getPropertySources()
                        .contains(source.getName())) {
                    environment.getPropertySources().addLast(source);
                }
            }
        } catch (IOException ex) {
            throw new IllegalStateException(
                    "Cannot load feature defaults", ex);
        }
    }
}
```

This is an **optional example**, not part of the two-processor demo registered in section 8.

Notes:

- The loader can return **multiple `PropertySource`s**, such as multi-document YAML; do not assume only one element exists.
- `addLast` gives lower priority than existing sources.
- Clarify whether a missing file is skipped or fails fast.
- If the file uses complex profile/activation/import features, a simple EPP does not automatically reproduce full Config Data behavior.
- For standard `.properties`/YAML config files, prefer `spring.config.import` or Spring Boot's default config loading rules before writing custom loaders.

## 19. Checking Whether a PropertySource Was Added

In a bean running after startup:

```java
@Bean
ApplicationRunner inspect(ConfigurableEnvironment environment) {
    return args -> {
        System.out.println(
                "defaults registered: "
                + environment.getPropertySources()
                        .contains("demo-epp-defaults"));

        System.out.println(
                "derived registered: "
                + environment.getPropertySources()
                        .contains("demo-epp-derived"));
    };
}
```

Place this method in a `@Configuration` or `@SpringBootApplication` class, not as a standalone Java file.

It helps distinguish:

```text
Processor was not registered / did not run
```

from:

```text
Processor ran, but the key was overridden by a higher-priority source
```

If both sources are added yet `demo.mode` is not what you expected, inspect **source position** and `PropertySource` precedence instead of concluding the EPP never ran.

### 19.1. Safely Inspecting Source Order

You can list **source names** in development environments:

```java
for (PropertySource<?> source :
        environment.getPropertySources()) {
    System.out.println(source.getName());
}
```

This snippet prints only names, not values. Do not dump the entire `source.getSource()` to logs as it may contain secrets.

PropertySource names added by the framework can be complex and vary by version/format/config data. Do not build product contracts around an undocumented internal name.

## 20. Testing Processors with a Mock Environment

The invocation mechanism:

```java
postProcessEnvironment(environment, application)
```

is a regular Java API, so you can test a processor without booting all of Spring Boot.

JUnit 5 example:

```java
package example.environment;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.core.env.MapPropertySource;
import org.springframework.mock.env.MockEnvironment;

class EnvironmentProcessorsTest {

    @Test
    void defaultsAndDerivedSourcesWork() {
        MockEnvironment environment = new MockEnvironment();

        environment.getPropertySources().addFirst(
                new MapPropertySource("test-input", Map.of(
                        "demo.region", "eu-west-1",
                        "demo.mode", "qa"
                )));

        SpringApplication application =
                new SpringApplication(Object.class);

        var defaults = new DefaultsEnvironmentPostProcessor();
        var derived = new DerivedEnvironmentPostProcessor();

        assertTrue(defaults.getOrder() < derived.getOrder());

        defaults.postProcessEnvironment(environment, application);
        derived.postProcessEnvironment(environment, application);

        assertEquals("eu-west-1",
                environment.getProperty("demo.region"));
        assertEquals("qa",
                environment.getProperty("demo.mode"));
        assertEquals("2",
                environment.getProperty("demo.retry-count"));
        assertEquals("eu-west-1/qa",
                environment.getProperty("demo.instance-label"));
    }

    @Test
    void explicitlyConfiguredLabelWins() {
        MockEnvironment environment = new MockEnvironment();

        environment.getPropertySources().addFirst(
                new MapPropertySource("test-input", Map.of(
                        "demo.region", "eu-west-1",
                        "demo.mode", "qa",
                        "demo.instance-label", "operator-defined"
                )));

        SpringApplication application =
                new SpringApplication(Object.class);

        new DefaultsEnvironmentPostProcessor()
                .postProcessEnvironment(environment, application);
        new DerivedEnvironmentPostProcessor()
                .postProcessEnvironment(environment, application);

        assertEquals("operator-defined",
                environment.getProperty("demo.instance-label"));
    }
}
```

To use `MockEnvironment` and JUnit 5, the project needs an appropriate test dependency, for example:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

These two tests prove **source-addition logic and effective values** in a manually constructed test environment.

They **do not prove** `META-INF/spring.factories` is packaged and that the framework discovers both processors in a real application.

## 21. Integration Testing: Verifying `spring.factories`

To verify discovery, launch a real Spring Boot application in a test or run the packaged artifact.

JUnit 5 example with Spring Boot:

```java
package example.environment;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;

class RegisteredEnvironmentProcessorsTest {

    @Test
    void registeredProcessorsApplyWhenBootStarts() {
        try (ConfigurableApplicationContext context =
                new SpringApplicationBuilder(
                        EnvironmentDemoApplication.class)
                        .web(WebApplicationType.NONE)
                        .run("--demo.region=eu-north-1",
                             "--demo.mode=integration")) {

            assertEquals("eu-north-1/integration",
                    context.getEnvironment()
                            .getProperty("demo.instance-label"));

            assertEquals("2",
                    context.getEnvironment()
                            .getProperty("demo.retry-count"));
        }
    }
}
```

The test uses `SpringApplicationBuilder` to initialize the Spring Boot lifecycle, thereby discovering both processors via `spring.factories` when the classpath is configured properly.

Why is this test different from a unit test?

- A unit test calls the EPP directly, so it can still pass when `spring.factories` is forgotten.
- An integration test requires Boot to **discover the classes itself** via metadata in resources.
- The integration test also confirms ordering relative to Config Data and values in a real context.

If the integration test fails while the unit test passes, prioritize checking:

1. Is `src/main/resources/META-INF/spring.factories` included on the test classpath?
2. Is the interface key exact?
3. Are class names fully qualified, with no package or spelling typos?
4. Did the build copy resources?
5. Are there any early constructor/lifecycle errors?
6. Does `getOrder()` properly follow Config Data?
7. Is another configuration source overriding the expected value?

### 21.1. Why Might `ApplicationContextRunner` Not Suffice for Discovery Testing?

`ApplicationContextRunner` is very useful for testing auto-configuration and bean definitions. However, creating a plain context via the runner **is not equivalent** to running the full `SpringApplication` event chain that triggers every `EnvironmentPostProcessor` via `spring.factories`.

If you need to test **actual EPP discovery**, use a test with a corresponding Spring Boot startup lifecycle instead of using `ApplicationContextRunner` without invoking the EPP yourself.

## 22. Listener Order and EPP Order Are Not the Same

Spring Boot has `EnvironmentPostProcessorApplicationListener`, a listener participating in startup that triggers registered EPP implementations.

Distinction:

- **Listener order** determines when this listener is called relative to other application listeners.
- **EPP order** determines in what order the `EnvironmentPostProcessor` implementations inside are executed.

These are two different ordering levels.

If one team adds a custom `ApplicationListener<ApplicationEnvironmentPreparedEvent>` and another team adds an EPP, do not simply compare the order numbers of the two classes and assume exact ordering as if both were EPPs. Inspect the lifecycle and listener ordering at the proper layer.

In most cases where you only need to customize `Environment` with an EPP, use `Ordered` or `@Order` directly on the EPP instead of altering Boot's internal listener order.

## 23. Common Registration Mistakes

| Symptom | Cause | How to Fix |
| --- | --- | --- |
| EPP is not called | Missing `spring.factories` | Create `src/main/resources/META-INF/spring.factories` |
| File exists yet EPP does not run | Wrong package name in key | Use `org.springframework.boot.env.EnvironmentPostProcessor` |
| EPP mistakenly put in `AutoConfiguration.imports` | Wrong extension SPI | Put EPP in `spring.factories` |
| Class has `@Component` yet does not run at desired time | Component scan is late and not EPP discovery | Use `spring.factories` |
| `ClassNotFoundException` | Value in factories does not match package/class | Fix fully qualified class name |
| Constructor cannot instantiate | Expected business bean DI or unsupported constructor | Use no-arg or Boot-API-supported constructor |
| B reads missing key | B ran before A or before Config Data | Set appropriate `getOrder()` |
| CLI fails to override defaults | Custom source used `addFirst` | Use `addLast` if only wanting fallbacks |
| Very early logging behaves unexpectedly | Logging not yet fully configured | Check `DeferredLogFactory` |
| Direct EPP test passes yet real app lacks values | Test did not check factories discovery | Add startup integration test |
| File missing after build | Resources not copied/packaged | Inspect `target/classes/META-INF` and JAR |
| Source present yet value differs | Higher-priority source or derived from another source | Check `PropertySource` order and config data |
| Boot still uses old config location | `spring.config.*` set after Boot already used it | Design earlier processor or use CLI/env |
| Re-running processor causes errors | No idempotence policy | Guard source name or replace deliberately |
| Startup fails due to network | EPP calls external service too early | Move to Config Data API or proper layer |

## 24. Design Mistake: Guessing Order Based on `spring.factories`

Do not write:

```properties
org.springframework.boot.env.EnvironmentPostProcessor=example.environment.FirstPostProcessor,example.environment.SecondPostProcessor
```

and deduce:

```text
First always runs before Second because it appears first.
```

Instead:

```java
public int getOrder() {
    return ConfigDataEnvironmentPostProcessor.ORDER + 1;
}
```

and:

```java
public int getOrder() {
    return ConfigDataEnvironmentPostProcessor.ORDER + 20;
}
```

Lower order runs earlier. If processors have dependencies, define explicit orders.

Do not use `Thread.sleep`, marker files, or static variables to try to enforce startup order. Boot already provides an ordering contract for EPPs.

## 25. Design Mistake: Assuming Running Late Means High Priority

Suppose B runs after A, yet both call `addLast`. If A adds `demo.timeout=5s` and B adds `demo.timeout=30s` at the end, **you cannot conclude B wins just because it ran later**. For the same key, the source sitting higher in precedence order still decides `Environment#getProperty`.

Example:

```text
PropertySources after A:
  - applicationConfig
  - A

PropertySources after B addLast:
  - applicationConfig
  - A
  - B
```

In this illustrative structure, if both A and B declare `demo.timeout`, A outranks B even though B ran later.

If you want B to override A without beating CLI, **pick a relative position** intentionally using `addBefore` or `addAfter`, and inspect existing sources. Avoid blindly using `addFirst` since it can override command-line properties too.

## 26. Should You Use EPP for Every Custom Configuration?

No. Pick the API matching the requirement type.

| Need | Appropriate Tool |
| --- | --- |
| Reading standard config files in Boot default locations | `application.properties` / YAML |
| Importing another standard config file | `spring.config.import` |
| Environment variables in container/OS | Environment variable |
| Grouping typed configuration | `@ConfigurationProperties` |
| Converting strings to custom domain types | `Converter` + `@ConfigurationPropertiesBinding` |
| Adding a very early property source | `EnvironmentPostProcessor` |
| Handling custom config locations such as `custom:` | `ConfigDataLocationResolver` + `ConfigDataLoader` |
| Customizing beans/context after `ApplicationContext` exists | Appropriate initializer/bean extension |
| Verifying behavior after context startup | `ApplicationRunner`/`CommandLineRunner` |

A simple solution via `spring.config.import=optional:file:./extra.properties` is usually easier to maintain than writing an EPP solely to read one extra ordinary `.properties` file.

EPP has clear value when needing **an Environment customization mechanism**, early processing order, or integrating a config source with custom logic.

## 27. Security and Operational Rules

Environment manipulation deeply affects the application. Essential practices:

1. **Do not hardcode secrets in fallback maps.** Fallbacks can be environment names, retry counts, feature flags; passwords/tokens belong in safer sources.
2. **Do not print all property values to logs.** It easily exposes sensitive info.
3. **Do not unexpectedly override CLI and env vars** with `addFirst` when the goal is defaults.
4. **Use dedicated prefixes for PropertySource names** to avoid colliding with Boot or other modules.
5. **Limit dependencies** in EPP, avoiding repositories and heavy network calls.
6. **Define policies for missing files/values**: skip, fallback, or fail fast.
7. **Document order** in source code using Boot constant names when depending on Config Data.
8. **Write integration tests for factories registration** rather than testing only the processor algorithm.
9. **Monitor startup logs in secure environments**, with proper handling of sensitive fields.
10. **Do not set config-data location properties late** expecting Boot to reload everything.
11. **Do not create circular dependencies:** a processor needing config that depends on a source created by another processor running later.
12. **Watch for Boot upgrade changes**, as lifecycles and internal processors can change; re-verify the contract of your target version.

## 28. Self-Check Exercises

### Exercise 1 — Registration Path

**Question:** A class `MyEnvironmentPostProcessor` implements `EnvironmentPostProcessor`. For Spring Boot 3.3 to discover it automatically, where do you declare it?

**Answer:** In `src/main/resources/META-INF/spring.factories`, with the full key `org.springframework.boot.env.EnvironmentPostProcessor`.

### Exercise 2 — Execution Order

**Question:** Processor A has `getOrder()=10`, B has `getOrder()=20`. Which processor is ordered first?

**Answer:** A, because a smaller order number has higher execution priority.

### Exercise 3 — Order in factories

**Question:** If `spring.factories` lists B before A, yet A has a smaller order than B, which information determines the order?

**Answer:** The `Ordered`/`@Order` contract, not the position in the list.

### Exercise 4 — Config Data

**Question:** A processor wants to read `demo.region` present only in `application.properties`. Should it run before or after `ConfigDataEnvironmentPostProcessor`?

**Answer:** After, for instance using `ConfigDataEnvironmentPostProcessor.ORDER + 1`.

### Exercise 5 — Fallback

**Question:** To provide `demo.retry-count=2` only when no other source has it, choose `addFirst` or `addLast`?

**Answer:** Usually choose `addLast` to have lower priority than existing sources.

### Exercise 6 — Two Ordering Axes

**Question:** B runs after A, yet B uses `addLast`. Does B always override A's keys?

**Answer:** No. EPP execution order and `PropertySource` position are two separate mechanisms.

### Exercise 7 — Registration Namespace

**Question:** Can you put an EPP into `AutoConfiguration.imports` instead of `spring.factories`?

**Answer:** That is not the standard Spring Boot 3.3 EPP registration mechanism. `AutoConfiguration.imports` is for auto-configuration.

### Exercise 8 — Bean Dependencies

**Question:** Should you inject an application repository into an EPP constructor and query the DB right at startup?

**Answer:** Do not assume repositories are ready. EPP is instantiated very early. Design lightweight processing with minimal dependencies and pick the appropriate extension API.

### Exercise 9 — Overridden Bug

**Question:** `demo.mode` is passed on the CLI, yet the result is still the fallback added by EPP. What should you inspect?

**Answer:** Where the source was added (`addFirst`/`addLast`), when the source was added, and `PropertySource` precedence. Do not just change `getOrder()`.

### Exercise 10 — Logging

**Question:** Why might an EPP need `DeferredLogFactory`?

**Answer:** Because environment processing occurs very early, before logging is fully configured. Deferred logging fits that lifecycle.

### Exercise 11 — Unit and Integration Tests

**Question:** Does a passing unit test calling `postProcessEnvironment` directly prove factories registration is correct?

**Answer:** Not yet. You need a startup test with the real Spring Boot lifecycle or verify the artifact contains `META-INF/spring.factories`.

### Exercise 12 — Source Name

**Question:** Why use a constant `SOURCE_NAME` and check `contains`?

**Answer:** To clearly identify the source and prevent duplicate additions that would unintentionally shift source positions if the method is called again.

### Exercise 13 — Overriding Config Location

**Question:** A processor running after Config Data adds `spring.config.location`. Must Boot reload config from the new location?

**Answer:** No. Properties governing Config Data are consumed very early. If changes are needed, perform them at the right phase or supply them via CLI/env/system properties per contract.

### Exercise 14 — Choosing Tools

**Question:** You only need to import an `extra.properties` file on the filesystem. Must you write an EPP?

**Answer:** No. Usually `spring.config.import` or standard Config Data suffices and is simpler.

## 29. Practical Implementation Checklist

- [ ] Identified why EPP is needed instead of Config Data/`@ConfigurationProperties`.
- [ ] Class properly implements `org.springframework.boot.env.EnvironmentPostProcessor`.
- [ ] `postProcessEnvironment` performs only work valid in the bootstrap phase.
- [ ] Full class name registered in `META-INF/spring.factories`.
- [ ] Key in factories uses the exact `org.springframework.boot.env` package.
- [ ] Decided whether EPP runs before or after Config Data.
- [ ] Used `Ordered` or `@Order` with an intentional value.
- [ ] Dependent processors have distinct, explicit orders.
- [ ] Does not depend on class name ordering in factories.
- [ ] Chose `addFirst`, `addLast`, or relative positioning appropriately.
- [ ] Chose a stable, non-colliding PropertySource name.
- [ ] Has a re-run policy: add once, replace, or merge.
- [ ] Does not pull repositories/HTTP clients/business beans into EPP.
- [ ] Does not print secrets or dump the entire `Environment`.
- [ ] If early logging is needed, considered `DeferredLogFactory`.
- [ ] Has unit tests for `Environment` modification logic.
- [ ] Has integration tests verifying discovery from factories.
- [ ] Verified build output/JAR carries `META-INF/spring.factories`.
- [ ] Clearly defined which source wins when CLI/env/file share a key.
- [ ] Does not try to reload Config Data automatically when processor runs late.
- [ ] Has documentation explaining the EPP's scope and reason for existing.

## 30. Summary

**Registration** and **ordering** are two separate pieces of `EnvironmentPostProcessor`:

```text
META-INF/spring.factories
      |
      v
Boot discovers EPP implementations
      |
      v
Sorted via Ordered / @Order
      |
      v
Runs postProcessEnvironment in order
      |
      v
Each EPP adds/modifies PropertySources
      |
      v
PropertySource precedence decides final value
      |
      v
Environment is consumed by beans/conditions/binder
```

Three principles to remember:

1. **In Spring Boot 3.3, EPPs are registered via `META-INF/spring.factories`**, with the key `org.springframework.boot.env.EnvironmentPostProcessor`.
2. **Use `Ordered` or `@Order` to define invocation order**, lower priority numbers running first; if `application.properties` needs to be loaded beforehand, use an order **after** `ConfigDataEnvironmentPostProcessor.ORDER`.
3. **Processor invocation order does not equal value precedence order**. `addFirst`, `addLast`, and operations on `MutablePropertySources` determine the configuration source's position.

A reliable EPP needs a clear purpose, sensible order, deliberate `PropertySource` manipulation, minimal bootstrap dependencies, and thorough testing. Mastering these principles lets you extend Spring Boot's `Environment` without breaking existing externalized configuration rules.

## References

- Spring Boot 3.3.13 Java API — `EnvironmentPostProcessor`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/env/EnvironmentPostProcessor.html
- Spring Boot 3.3.13 Java API — `EnvironmentPostProcessorApplicationListener`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/env/EnvironmentPostProcessorApplicationListener.html
- Spring Boot 3.3.13 Java API — `ConfigDataEnvironmentPostProcessor`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/config/ConfigDataEnvironmentPostProcessor.html
- Spring Boot 3.3 Reference — Externalized Configuration: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 Reference — Customize the Environment or ApplicationContext Before It Starts: https://docs.spring.io/spring-boot/3.3/how-to/application.html
- Spring Framework API — `MutablePropertySources`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/env/MutablePropertySources.html
