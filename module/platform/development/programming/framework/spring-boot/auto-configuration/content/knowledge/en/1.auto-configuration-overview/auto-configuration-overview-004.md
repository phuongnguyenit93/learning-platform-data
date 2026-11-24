# Distinguishing auto-configuration from component scanning, dependency injection, and property binding

In Spring Boot, **auto-configuration**, **component scanning**, **dependency injection (DI)**, and **configuration properties binding** often occur during the same startup process. As a result, beginners easily think they are the same thing. In reality, each mechanism answers a different question:

- **Auto-configuration:** Which default configurations and beans should Spring Boot provide given the libraries, properties, and existing beans?
- **Component scanning:** Which classes written by the application, marked as components, reside in which packages for Spring to register them?
- **Dependency injection:** When creating a bean, where does Spring obtain dependent beans and pass them into constructors/parameters?
- **Property binding:** How are values from `application.properties`, YAML, environment variables, or the command line converted into strongly typed configuration data?

The goal of this lesson is to identify **the source of bean registration**, **the conditions for creating a bean**, **where dependencies are injected**, and **where configuration data is bound**. These four questions are independent in responsibility yet connected in execution.

## 1. Comparison table

| Mechanism | Common triggers/tools | What does it produce? | What does it not do by itself? |
| --- | --- | --- | --- |
| Auto-configuration | `@EnableAutoConfiguration` (brought in by `@SpringBootApplication`), `@AutoConfiguration`, `@Conditional...` | Default infrastructure beans/bean definitions based on conditions | Does not arbitrarily scan every class written by the application; does not guarantee any starter creates every bean |
| Component scanning | `@ComponentScan`, `@Component`, `@Service`, `@Repository`, `@Controller`, `@Configuration` | Bean definitions from classes discovered within the package scope | Does not automatically decide Boot infrastructure configuration based on classpath |
| Dependency injection | Constructor injection, `@Bean` parameters, sometimes `@Autowired` | Wires a bean with suitable dependent beans | Does not automatically create a dependency just because a type appears in a constructor |
| Property binding | `@ConfigurationProperties` with `@ConfigurationPropertiesScan`/`@EnableConfigurationProperties` | Strongly typed configuration objects populated from property sources | Does not by itself guarantee the configuration class is registered as a bean |

**Core relationship:** Both component scanning and auto-configuration can supply **bean definitions**. DI is the mechanism that **uses beans** to assemble objects. Property binding is the mechanism that **converts configuration data** into typed state. A bean from Boot auto-config can still be injected via DI into an application bean; there is no contradiction.

## 2. Why can `@SpringBootApplication` be confusing?

```java
@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`@SpringBootApplication` combines three important meanings: `@SpringBootConfiguration`, `@EnableAutoConfiguration`, and `@ComponentScan`. Because both scanning and auto-configuration are triggered from the same annotation, they can look similar even though their bean lookup paths are different.

- **Scanning** by default inspects the package containing `DemoApplication` and its subpackages. A `@Service` outside this scope is normally not discovered.
- **Auto-configuration** selects Boot/library configuration classes from a separate imports list, not because those classes sit under the application package. In Spring Boot 3.x, the standard auto-config registration file is `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.
- Conditions such as `@ConditionalOnClass`, `@ConditionalOnBean`, `@ConditionalOnMissingBean`, and `@ConditionalOnProperty` can enable, disable, or allow a default bean to back off.
- **DI** resolves dependencies based on matching beans in `ApplicationContext`.
- **Binding** converts properties into `String`, numbers, enums, `Duration`, collections, records, etc. according to declarations.

The following diagram shows the **logical relationships**, without asserting a rigid internal order for each step:

```text
        SpringApplication + Environment
                  |
                  v
          ApplicationContext
            /           \
           v             v
   @ComponentScan    Auto-config imports
   finds @Service,    + @Conditional...
   @Component...           |
           \             /
            v           v
             Bean definitions
                    |
        @ConfigurationProperties:
        registration + data binding
                    |
                    v
        Bean creation + DI
                    |
                    v
             Application runs
```

Thinking "Spring scans everything first, then finishes auto-config, then binds everything, and finally injects" is **oversimplified**: Spring processes bean definitions, conditions, bean creation, binding, and injection across interconnected phases. Use the diagram to understand roles, not as a strict execution-order chart.

## 3. Complete example with Java 17+ and Spring Boot 3.3.x

Goal: `GreetingService` is discovered by **component scanning**; `GreetingProperties` receives data from a file via **property binding**; Spring uses **DI** to pass properties into the service; Boot **auto-configures** an `ObjectMapper` because Jackson is present.

The example uses Maven, Spring Boot 3.3.13, and Java 17. Directory layout:

```text
auto-config-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/demo/
    │   ├── DemoApplication.java
    │   ├── GreetingProperties.java
    │   └── GreetingService.java
    └── resources/application.properties
```

**`pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>auto-config-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-web` provides Jackson-related dependencies; we will turn off web mode so the example exits once finished.

**`src/main/java/com/example/demo/GreetingProperties.java`**

```java
package com.example.demo;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "greeting")
public record GreetingProperties(String salutation, String target) {
}
```

This record does not have `@Component`. `@ConfigurationProperties` describes the `greeting.*` key group and the target data type. For Spring to create the corresponding bean, it still needs to be registered via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties(GreetingProperties.class)`.

**`src/main/java/com/example/demo/GreetingService.java`**

```java
package com.example.demo;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    private final GreetingProperties properties;

    public GreetingService(GreetingProperties properties) {
        this.properties = properties;
    }

    public String greet() {
        return properties.salutation() + ", " + properties.target() + "!";
    }
}
```

`@Service` is a specialized form of `@Component`: scanning finds the class and registers the bean. The constructor asks Spring to supply `GreetingProperties`: that action is **dependency injection**, completely distinct from scanning discovering `GreetingService`.

**`src/main/java/com/example/demo/DemoApplication.java`**

```java
package com.example.demo;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner show(GreetingService service, ObjectMapper mapper) {
        return args -> {
            System.out.println("GREETING=" + service.greet());
            System.out.println("MAPPER=" + mapper.getClass().getSimpleName());
        };
    }
}
```

`@ConfigurationPropertiesScan` finds configuration classes under the root package and registers `GreetingProperties` for the binder. `@Bean` explicitly declares `ApplicationRunner`; Spring provides the `GreetingService` and `ObjectMapper` parameters via DI. The Jackson object in the example comes from **auto-configuration**, not our `@Service` class.

**`src/main/resources/application.properties`**

```properties
spring.main.banner-mode=off
spring.main.web-application-type=none
logging.level.root=ERROR
greeting.salutation=Xin chào
greeting.target=Spring Boot
```

Run in the directory containing `pom.xml`:

```bash
mvn -q spring-boot:run
```

The two lines printed by the program itself (excluding environment/Maven-specific messages):

```text
GREETING=Xin chào, Spring Boot!
MAPPER=ObjectMapper
```

**Tracing the four mechanisms:**

1. Component scanning finds `GreetingService` via `@Service` and the `com.example.demo` package.
2. `@ConfigurationPropertiesScan` registers `GreetingProperties`; the binder reads `greeting.salutation` and `greeting.target` from the configuration source and creates the record with matching values.
3. Jackson on the classpath satisfies conditions for Boot to automatically create `ObjectMapper` via auto-configuration.
4. DI passes `GreetingProperties` into `GreetingService`'s constructor; then passes `GreetingService` and `ObjectMapper` into the `show(...)` method. The runner prints the result once the context is ready.

**Try changing a value:** change `greeting.target=Java` and run again. The first line becomes `GREETING=Xin chào, Java!`, because **the bound data** changed. We did not need to change the scan scope or rewrite auto-configuration.

## 4. Separating commonly confused differences

### 4.1. Scanning is not auto-configuration

Class written by the application:

```java
@Service
public class PriceService {
    // Component scanning can register this bean.
}
```

An auto-configuration in a library typically follows a conditional pattern like this. This is **only an illustrative snippet**; `SomeClient` needs to be replaced by a real class from a specific dependency:

```java
@AutoConfiguration
@ConditionalOnClass(SomeClient.class)
public class SomeClientAutoConfiguration {
    @Bean
    @ConditionalOnMissingBean
    SomeClient someClient() {
        return new SomeClient();
    }
}
```

`@ConditionalOnClass` requires the library type to exist; `@ConditionalOnMissingBean` usually lets the default configuration back off for a user bean. Other auto-configs can add conditions on properties, beans, web application type, etc. Adding a starter **can** trigger auto-config; it does not mean every bean is created unconditionally.

`@EnableAutoConfiguration` does not "rescue" a `@Service` located outside the component scanning scope. Conversely, an auto-config class in a JAR outside the application's package can still be imported via Boot's mechanism.

### 4.2. DI is not how beans are discovered

```java
public OrderService(PaymentGateway gateway) {
    this.gateway = gateway;
}
```

The constructor expresses that `OrderService` requires a `PaymentGateway` bean. Spring can only satisfy it if **a suitable candidate already exists** in the context, such as from `@Component`, a `@Bean` method, or auto-config. If none exists, `NoSuchBeanDefinitionException`/`UnsatisfiedDependencyException` may occur; if multiple candidates of the same type exist, disambiguation is needed via `@Primary`, `@Qualifier`, or another explicit configuration. Constructor injection is well suited for required dependencies because it directly exposes the dependency contract.

### 4.3. Binding is not DI and is not equivalent to `@Value`

`@ConfigurationProperties(prefix = "mail")` groups keys such as `mail.host` and `mail.port` into a strongly typed object. The binder handles type conversion and can work with validation. Once that object is a bean, DI can pass **the entire configuration bean** into a service.

`@Value` with placeholders usually reads a single value; it fits small cases but does not fully replace the grouped property binding and metadata model of `@ConfigurationProperties`.

**Note on registration:** a Java class with only `@ConfigurationProperties` is not necessarily turned into a bean automatically. For typical configuration types, you can use:

- `@ConfigurationPropertiesScan` to scan valid properties classes within a package scope;
- `@EnableConfigurationProperties(MyProperties.class)` to register explicitly;
- or bind a bean registered through another appropriate mechanism.

`@ConfigurationPropertiesScan` serves a different purpose from `@ComponentScan`. Under Boot's default scanning mechanism, `@Component` classes are not targets of `@ConfigurationPropertiesScan`; however, an already-registered component bean can still be bound if configured appropriately.

### 4.4. Bean definition differs from bean data

For example, changing `mail.port=8080` to `mail.port=9090` does not necessarily add or remove beans: the same bean can receive a different configuration state. Conversely, a property used in `@ConditionalOnProperty` can decide **whether a bean is registered at all**. Therefore, read each property in its exact context: whether it is used **to bind values** or **as a condition for creating a bean**.

## 5. Before-and-after scenarios

| Change | Common consequence | Where to check? |
| --- | --- | --- |
| Move `GreetingService` outside the scan scope | No service bean, leading to a DI error when the runner needs it | Main class package, `@ComponentScan` |
| Remove `@ConfigurationPropertiesScan` without registering the record otherwise | No `GreetingProperties` for the constructor | `@EnableConfigurationProperties` or other registration methods |
| Change `greeting.target` | Greeting output changes | Binder, key name, config source, and precedence order |
| Add a starter/JAR containing the corresponding class | Some auto-configuration conditions may flip from non-matching to matching | Classpath and Condition Evaluation Report |
| Declare your own matching `ObjectMapper` bean | Jackson's default auto-config usually backs off via `@ConditionalOnMissingBean` | User bean, auto-config conditions |
| Two `PaymentGateway` beans exist without a clear selection rule | DI may report multiple candidates | Qualifier, primary, bean name/type |
| Turn a `@Service` into a plain class without declaring `@Bean` | The bean is no longer registered via scan | Annotations and other registration mechanisms |

You cannot infer from a bean's existence that it was **definitely created by scanning**. Ask which registration source is responsible.

## 6. Observing the mechanisms while debugging

**Checking auto-configuration:** enable debug when running:

```bash
mvn -q spring-boot:run -Dspring-boot.run.arguments=--debug
```

`Condition Evaluation Report` helps locate which auto-configs were applied or not applied and the related conditions. If Spring Boot Actuator is added and exposure is appropriately configured, the `/actuator/conditions` endpoint is another way to view conditions; this endpoint is **not public by default**.

**Checking scanning:** verify `@SpringBootApplication`'s package, locations of `@Service`/`@Component`, custom `@ComponentScan` declarations, and annotations like `@Profile` that might prevent a bean from appearing. Do not fix this by scanning every package of external libraries.

**Checking DI:** read exceptions about missing beans, multiple candidates, qualifiers, or circular dependencies; check whether any bean definition actually matches the requested type. A constructor parameter is **where a dependency is requested**, not proof that the bean will be created.

**Checking binding:** audit prefix, key names, active profiles, environment variables, target types, and validation. Invalid configuration can cause binding to fail, preventing the bean/service using it from initializing. When handling sensitive configuration, do not print tokens/passwords to logs.

**Checking default customization:** if Boot's infrastructure bean disappears after the application declares a bean of the same type, look for `@ConditionalOnMissingBean` and other conditions before concluding that auto-config is broken.

## 7. False conclusions to avoid

- **"`@SpringBootApplication` scans all packages."** No. Component scanning is by default limited to the root package.
- **"Auto-configuration is DI."** No. Auto-config can supply beans; DI delivers beans where needed.
- **"Having `@ConfigurationProperties` guarantees binding runs."** No, there must be an appropriate registration mechanism and valid configuration sources.
- **"All properties only assign values."** No. Some properties serve as conditions to enable/disable beans.
- **"Adding a starter always creates every desired bean."** No, auto-config typically depends on multiple conditions.
- **"User beans are always overridden by Boot."** No. Many auto-configs back off when a matching bean already exists, though each case should be checked.

## 8. Self-check questions

1. A `@Service` outside the scan scope causes another constructor to report a missing bean: the root cause begins in **scanning**, then manifests as a **DI error**.
2. `ObjectMapper` is available even without writing `@Bean`: check **Jackson auto-configuration** along with classpath/conditions; injecting the mapper is still **DI**.
3. `GreetingService` stays unchanged while the greeting changes in properties: that is a change in **binding data**, not scanning a new class.
4. Want to use a custom implementation instead of Boot's default: check the auto-config, especially `@ConditionalOnMissingBean`, and register an appropriate user bean.
5. Can `@ConfigurationPropertiesScan` replace `@ComponentScan`? **No**: the two scan mechanisms serve two different registration sources.

When reading a Spring Boot application, always separate the four questions: **Who registers the bean? Which conditions allow the bean to exist? Where are configuration values bound? Where is the bean injected?** Answering these four questions clearly distinguishes auto-configuration, component scanning, dependency injection, and property binding.