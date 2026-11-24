# Placing Auto-Configuration Classes Outside the Application's Component Scan Scope

## 1. Why Does an Auto-Configuration's Package Location Matter?

In Spring Boot, an **auto-configuration class** is a special Spring configuration class: it provides default beans and infrastructure setup when appropriate conditions are satisfied. Although it carries `@AutoConfiguration` (which has `@Configuration` semantics), this class **must enter the application through Boot's auto-configuration import mechanism**. According to official Spring Boot guidance, auto-configurations should live in a separate package namespace, not become targets of component scanning, and not themselves component-scan to pull additional beans into the container. If supporting configuration classes are needed, use `@Import` explicitly.

Distinguish the two paths:

```text
Path A — application component scanning
@SpringBootApplication
  -> @ComponentScan
     -> package containing the main class and subpackages
        -> @Component / @Service / @Repository / @Controller /
           @Configuration ...
        -> BeanDefinitions of application components

Path B — auto-configuration selection
@SpringBootApplication
  -> @EnableAutoConfiguration
     -> reads META-INF/spring/...AutoConfiguration.imports
        -> exclusions + conditions + relevant ordering
        -> imports matching @AutoConfiguration classes
        -> Conditional default BeanDefinitions
```

Both paths end up in **the same Spring `ApplicationContext`** and `BeanFactory`. The difference lies in **how configurations are discovered, selected, excluded, and processed**, not in the final container type.

**Core rule:** a library's `@AutoConfiguration` class should not sit inside the scope that the application's `@ComponentScan` will scan. If it is scanned as an ordinary `@Configuration`, it can enter processing through an unintended path, making ordering, conditions, and exclusions unpredictable and undermining clear control over auto-configuration.

## 2. How Is the Default Scan Scope Determined?

Given an application:

```java
package com.acme.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

`@SpringBootApplication` combines these primary roles:

- `@SpringBootConfiguration`: marks the application configuration.
- `@ComponentScan`: discovers components in the root package and subpackages.
- `@EnableAutoConfiguration`: enables auto-configuration selection via JAR metadata.

Without special overrides, component scanning starts from **`com.acme.shop`** and its subpackages:

```text
com.acme.shop                    <- @SpringBootApplication class
├── service                     <- scanned
├── config                      <- scanned
├── web                         <- scanned
└── repository                  <- scanned

com.acme.integration.autoconfigure  <- outside the package tree above
```

A class `com.acme.shop.service.OrderService` annotated with `@Service` can be discovered. However, `com.acme.integration.autoconfigure.ClientAutoConfiguration` does **not** belong to the `com.acme.shop` tree, so default component scanning will not load it. It can still be selected by Boot via the `AutoConfiguration.imports` file in its JAR.

Remember that a **Java package** is a qualified identifier hierarchy, not merely an IDE folder. A class in package `com.acme.shop.autoconfigure` lies *inside* the scan scope even if placed in a separate source module or JAR. Conversely, `com.acme.integration.autoconfigure` can live in the same repository yet remain *outside* the scan scope.

### A Misleading Structure

```text
com.acme
├── Application.java             (@SpringBootApplication)
├── feature
│   ├── FeatureService.java      (@Service)
│   └── FeatureAutoConfiguration.java  (@AutoConfiguration)
```

If the main class sits in `com.acme`, `@ComponentScan` can reach `com.acme.feature.FeatureAutoConfiguration`, because `@AutoConfiguration` is fundamentally a `@Configuration` class. Putting it in a package named `autoconfigure` is **not enough** to guarantee it will not be scanned. You must check the actual scan scope and package relationship.

Therefore:

- **Architecturally wrong:** merely renaming a class or creating an `autoconfigure` folder beneath the root package and assuming the import path is separated.
- **Architecturally right:** placing the auto-configuration class in its own package outside the application's scan scope and declaring its full name in the `.imports` file.

## 3. Auto-Configuration Is Discovered via Dedicated Metadata

With Spring Boot 3.x, library authors register auto-configurations in the resource:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Each line contains the fully qualified name of one class:

```text
com.acme.integrations.autoconfigure.ClientAutoConfiguration
com.acme.integrations.autoconfigure.ClientMetricsAutoConfiguration
```

At startup, `@EnableAutoConfiguration` triggers discovery and selection of these candidate names. `AutoConfigurationImportSelector` (a `DeferredImportSelector`) participates in processing that list; Boot can apply filtering, exclusions, and necessary ordering before Spring parses the selected configurations.

A typical class:

```java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.sdk.Client")
class ClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(ClientAdapter.class)
    ClientAdapter clientAdapter() {
        return new ClientAdapter();
    }
}
```

This is **illustrative code, not a standalone Java program**: `ClientAdapter` is a hypothetical type, and appropriate annotation imports are needed. The scenario shows:

1. Only when the required SDK library is present can the class condition match.
2. If the application already has a matching bean, `@ConditionalOnMissingBean` can prevent the default bean from **being registered**.
3. If all conditions are met, Spring records the bean definition and the container later instantiates the bean according to its lifecycle.

**The `.imports` file lists candidates; it does not immediately create beans.** A listed class can still be filtered out by exclusions or `@Conditional` checks during startup. Proper package separation ensures these decisions flow through the designed auto-configuration pipeline.

### Distinguishing Important Files

| File | Role |
| --- | --- |
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` | List of auto-configuration classes for Boot to consider importing |
| `META-INF/spring-autoconfigure-metadata.properties` | Condition metadata optionally generated by an annotation processor to support early filtering |
| `META-INF/spring-configuration-metadata.json` | Metadata supporting IDEs and tooling for configuration keys |
| `META-INF/spring.factories` | Still used by some Boot extensions; **not where new auto-configurations are registered** in Spring Boot 3.x |

Do not confuse registering an auto-configuration in `.imports` with configuring `@ComponentScan`: the two mechanisms serve different purposes.

## 4. Why Not Let Component Scanning "Find" Auto-Configuration Classes?

Suppose a library places `MyFeatureAutoConfiguration` inside the application's scan scope. Even though the class has `@AutoConfiguration`, component scanning can treat it as a `@Configuration` class and process it. That blurs the boundary between application configuration and library defaults.

Risks to be aware of:

| Possible consequence | Why it matters |
| --- | --- |
| Configuration discovered outside the auto-configuration import pipeline | Ordering intended for auto-configuration may no longer behave as designed |
| Exclusions do not govern every configuration registration path | Boot's `exclude` acts on the auto-configuration list; a class also scanned/imported via another path can still participate in configuration |
| Bean-dependent conditions become hard to reason about | `@ConditionalOnMissingBean` relies on bean definitions already processed at evaluation time |
| Features appear unexpectedly when changing the main package or scan settings | The library might suddenly be scanned after an application config change |
| Hard to diagnose where a configuration was loaded from | Easy to confuse component scanning, explicit `@Import`, and Boot imports |
| Hard to package a reusable starter for multiple apps | Different apps have different scan scopes, whereas auto-configuration needs a consistent discovery mechanism |

Do not claim every such project throws duplicate-bean errors: Spring has mechanisms for handling configurations and deduplication. The core issue is **violating the organizational contract of auto-configuration** and introducing an unintended loading path, rather than one fixed exception across all versions.

A common wrong fix:

```java
@SpringBootApplication(scanBasePackages = "com.acme")
public class ShopApplication {
}
```

If the library `com.acme.integrations.autoconfigure` sits beneath `com.acme`, widening scan to the shared package `com.acme` can cause the auto-configuration class to be scanned. Instead of scanning the entire organization namespace, restrict scan scope to application components or wire required parts via explicit `@Import`.

## 5. Package Organization for Applications and Libraries

### 5.1. One Repository, Multiple Modules

Recommended layout when developing a library:

```text
workspace/
├── shop-app/
│   └── src/main/java/com/acme/shop/
│       ├── ShopApplication.java             (@SpringBootApplication)
│       ├── service/OrderService.java        (@Service)
│       └── web/OrderController.java         (@RestController)
├── acme-client-core/
│   └── src/main/java/com/acme/client/
│       ├── AcmeClient.java                  (API)
│       └── DefaultAcmeClient.java           (implementation)
├── acme-client-autoconfigure/
│   ├── src/main/java/com/acme/client/autoconfigure/
│   │   └── AcmeClientAutoConfiguration.java (@AutoConfiguration)
│   └── src/main/resources/META-INF/spring/
│       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── acme-client-starter/
    └── pom.xml                              (dependency convenience)
```

Here, `shop-app`'s root package is `com.acme.shop`, while the auto-configuration sits in `com.acme.client.autoconfigure`. Separating modules is helpful when building a reusable starter, yet **a separate module alone is not enough**: if the package falls inside the scan tree, the scanner can still find classes from the JAR.

The **starter** mainly provides commonly used dependencies, the **auto-configure module** contains conditional default configurations, and the **core module** holds the library's APIs/implementations. This is a common organizational model, though not every project must use three modules.

### 5.2. Which Packages Should Be Scanned?

In `shop-app`, services/controllers/configs owned by the application should reside under `com.acme.shop`. Those components are intentionally scanned.

In the auto-configure library, avoid:

```java
@AutoConfiguration
@ComponentScan("com.acme.client")
public class AcmeClientAutoConfiguration {
}
```

This is an **anti-pattern when writing auto-configurations**: the auto-configure class can scan a whole swath of unintended components, bypassing explicit selection of what needs to be registered.

Instead, use `@Import` with well-defined supporting classes:

```java
@AutoConfiguration
@Import(AcmeClientSupportConfiguration.class)
public class AcmeClientAutoConfiguration {
}
```

`AcmeClientSupportConfiguration` is an illustrative class and must be appropriately defined/imported when applied. `@Import` makes clear to developers which supporting configurations are brought in; conditions can be placed on the auto-configuration and nested/imported classes as needed.

Avoid using `@ComponentScan` merely to "save listing imports", as it can pull in beans the application neither needs nor wants.

## 6. Runnable Example: Auto-Configuration Outside the Scan Package

The example uses **Java 17+**, **Spring Boot 3.3.13**, and **Maven** in a single simple module to focus on the mechanism. When building a real library, you can split the auto-configuration class into a separate JAR while following the exact same package and `.imports` rules.

Goals of the example:

- `demo.app.DemoApplication` is the main class with `@SpringBootApplication`.
- `demo.autoconfig.GreetingAutoConfiguration` sits outside `demo.app` so default component scanning does not find it.
- `META-INF/spring/...AutoConfiguration.imports` adds the auto-configuration class to Boot's candidate list.
- `demo.api.Greeting` is a plain Java API with no component stereotype.
- `demo.app.UserGreetingConfiguration` declares a custom bean when a property is enabled; the conditional auto-configuration backs off in favor of this bean.
- Using CLI runs, observe **default**, **auto-configuration excluded**, and **application bean overriding default**.

### 6.1. File Structure

```text
greeting-autoconfig-scan/
├── pom.xml
└── src/main/
    ├── java/
    │   └── demo/
    │       ├── api/
    │       │   └── Greeting.java
    │       ├── app/
    │       │   ├── DemoApplication.java
    │       │   └── UserGreetingConfiguration.java
    │       └── autoconfig/
    │           └── GreetingAutoConfiguration.java
    └── resources/
        └── META-INF/
            └── spring/
                └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

`demo.app` and `demo.autoconfig` are **two sibling packages**. A scanner starting at `demo.app` does not walk up to `demo` to scan all subpackages. Even though the auto-configuration class resides in the same Maven project and is present on the classpath, it does **not** become a component scan candidate under the default scope.

### 6.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <groupId>example</groupId>
    <artifactId>greeting-autoconfig-scan</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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

Only `spring-boot-starter` is needed to use the IoC container and core Boot APIs. Without a web starter, the example requires no HTTP port or web server. Java 17+ matches Spring Boot 3.3 compatibility and suffices for Java `record`s.

### 6.3. Plain Java API

**`src/main/java/demo/api/Greeting.java`**

```java
package demo.api;

public record Greeting(String text) {
}
```

`Greeting` is just a record. It has no `@Component`, `@Configuration`, or `@Bean`, so its mere presence on the classpath does not make Spring create a `Greeting` bean.

### 6.4. Auto-Configuration Class Outside Scan Scope

**`src/main/java/demo/autoconfig/GreetingAutoConfiguration.java`**

```java
package demo.autoconfig;

import demo.api.Greeting;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(Greeting.class)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Greeting.class)
    Greeting defaultGreeting() {
        return new Greeting("default");
    }
}
```

Explanation:

- `@AutoConfiguration`: the class belongs to default configurations selected by Boot, not a business component for the scanner to find.
- `@ConditionalOnClass(Greeting.class)`: applies only when the corresponding API class is on the classpath. In the example the class is always present, so this condition is true.
- `@ConditionalOnMissingBean(Greeting.class)`: registers the `defaultGreeting` bean only if no matching `Greeting` bean exists at evaluation time.
- `@Bean`: defines a factory method. Spring IoC instantiates the `Greeting` object after the valid definition is registered.

The auto-configuration class does not use `@ComponentScan`. If a library has additional supporting configurations, use `@Import` explicitly as recommended in section 5.

### 6.5. AutoConfiguration.imports File

**`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**

```text
demo.autoconfig.GreetingAutoConfiguration
```

Note the exact path, including uppercase letters in `AutoConfiguration.imports` and the class's full package name. Without this line, an auto-configuration outside component-scan scope **has no standard auto-configuration discovery path** through this JAR.

In Spring Boot 3.x, auto-configurations should be registered via `.imports`, not simply placed in a scanned package. `spring.factories` is still used by some other extensions; do not use it as the primary registration path for new auto-configurations in this example.

### 6.6. Bean Explicitly Supplied by the Application

**`src/main/java/demo/app/UserGreetingConfiguration.java`**

```java
package demo.app;

import demo.api.Greeting;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    name = "demo.greeting.custom",
    havingValue = "true"
)
public class UserGreetingConfiguration {

    @Bean
    Greeting userGreeting() {
        return new Greeting("custom");
    }
}
```

Because `UserGreetingConfiguration` is in `demo.app`, component scan can find it. However, this configuration **registers the bean only** when `demo.greeting.custom=true`.

This property is **defined by the example itself**, not a built-in Spring Boot property. When the property is disabled, this application configuration class contributes no bean. When enabled, it provides `Greeting("custom")`; the auto-configuration, relying on `@ConditionalOnMissingBean`, backs off in favor of the existing matching definition.

### 6.7. Main Application

**`src/main/java/demo/app/DemoApplication.java`**

```java
package demo.app;

import demo.api.Greeting;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showGreeting(ObjectProvider<Greeting> provider) {
        return args -> {
            Greeting bean = provider.getIfAvailable();
            String message = bean == null ? "missing" : bean.text();
            System.out.println("GREETING: " + message);
        };
    }
}
```

`ObjectProvider<Greeting>` is used because in the auto-configuration exclusion case there may be no `Greeting` bean left. That lets the runner execute and print `missing` rather than failing due to an absent required dependency.

`ApplicationRunner` is an application bean invoked by Boot after the context refresh succeeds. It also illustrates that beans from auto-configuration, component scanning, and `@Bean` methods all enter the same container.

### 6.8. Build and Run

In the directory containing `pom.xml`, using Java 17+ and Maven:

```bash
mvn -q -DskipTests package
java -jar target/greeting-autoconfig-scan-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none
```

Besides startup logs and the banner, the line printed by the program itself is:

```text
GREETING: default
```

Reason: `GreetingAutoConfiguration` was loaded **via `.imports`**, the class condition matched, and no application-declared `Greeting` bean existed, so `defaultGreeting()` supplied the default bean.

**Try excluding that exact auto-configuration:**

```bash
java -jar target/greeting-autoconfig-scan-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none \
  --spring.autoconfigure.exclude=demo.autoconfig.GreetingAutoConfiguration
```

Line printed by the program:

```text
GREETING: missing
```

Reason: `GreetingAutoConfiguration` was excluded from the import list. It also lies **outside component scan scope**, so no other scanning path picked up the class automatically. No other application configuration supplied `Greeting`, so `ObjectProvider#getIfAvailable()` returned `null`.

**Try an application bean replacing the default:**

```bash
java -jar target/greeting-autoconfig-scan-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none \
  --demo.greeting.custom=true
```

Line printed by the program:

```text
GREETING: custom
```

Reason: `UserGreetingConfiguration` lies within component scan scope and the property allowed `userGreeting` to register; when auto-configuration evaluated `@ConditionalOnMissingBean`, a matching `Greeting` bean already existed, so `defaultGreeting` backed off.

**Try one more combined scenario:**

```bash
java -jar target/greeting-autoconfig-scan-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none \
  --demo.greeting.custom=true \
  --spring.autoconfigure.exclude=demo.autoconfig.GreetingAutoConfiguration
```

The result is still:

```text
GREETING: custom
```

This proves the application's bean does not depend on whether Boot imports the default auto-configuration.

**The four runs** use the same JAR yet yield different outcomes via conditions, exclusions, and application bean definitions. No component scanning changes were needed between runs.

## 7. Wrong Scenario: Placing Auto-Configuration in an Application Subpackage

Inspect this layout visually:

```text
demo/
└── app/
    ├── DemoApplication.java          (@SpringBootApplication)
    ├── UserGreetingConfiguration.java
    └── autoconfig/
        └── GreetingAutoConfiguration.java (@AutoConfiguration)
```

Here the auto-configuration's package name is `demo.app.autoconfig`. Because it sits beneath `demo.app`, the application's component scanner can pick up the class as a `@Configuration`. Even if you also update `.imports` to list the new name, the layout still gives the auto-configuration an unwanted extra discovery path.

**Do not merely "delete `.imports`" and rely on scanning to make the program run.** Doing so turns a class meant to be conditionally selected by Boot into configuration loaded like an ordinary component, losing the discovery/exclusion/ordering guarantees designed for auto-configuration.

The proper fix:

1. Move the class to a package outside scan scope, e.g., `demo.autoconfig.GreetingAutoConfiguration`.
2. Update the package statement, Java imports, and `.imports` file to the new fully qualified name.
3. Confirm the application's component scan is not widened to `demo.autoconfig`.
4. Keep necessary `@Conditional...` annotations so defaults back off for application configuration.
5. Separately test the import path, the exclusion path, and cases where the application supplies a custom bean.

There is no need to add another `@SpringBootApplication` in the library module. The library provides `@AutoConfiguration` and metadata, while the application is responsible for having a proper entrypoint.

## 8. scanBasePackages Can Break This Boundary

Even when an `@AutoConfiguration` class already sits in a separate package, an application can still **widen scan scope** too broadly:

```java
@SpringBootApplication(scanBasePackages = "demo")
public class DemoApplication {
}
```

This is a conceptual snippet, **not a replacement for the main file in the runnable example**. If the scanner starts at `demo`, it can discover `demo.autoconfig.GreetingAutoConfiguration`, because an auto-configuration class carries `@Configuration` semantics.

Two commonly used attributes:

```java
@SpringBootApplication(
    scanBasePackages = {"demo.app", "demo.otherapp"}
)
```

and:

```java
@SpringBootApplication(
    scanBasePackageClasses = {SomeApplicationMarker.class}
)
```

are illustrative snippets requiring appropriate classes/imports. They adjust **component scanning**. They do not convert candidate auto-configurations in `.imports` into component-scanned classes, nor do they inherently alter every JPA entity or Spring Data repository scanning mechanism.

A useful review rule: whenever changing `scanBasePackages`, check whether the new scan scope includes any `*.autoconfig`, `*.autoconfigure`, or library namespace carrying `@AutoConfiguration`. Package names are only a clue; the **actual package hierarchy** decides whether the scanner reaches that class.

## 9. What If the Library Needs Supporting Components?

Library authors often have extra encoders, serializers, client factories, validators, or adapters. You should not dump all those classes under one package and scan them broadly from the auto-configuration.

### Use @Bean for Objects Needing Factory Methods

```java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.Client")
class VendorClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(VendorClientAdapter.class)
    VendorClientAdapter vendorClientAdapter() {
        return new VendorClientAdapter();
    }
}
```

This snippet illustrates the API, assuming `VendorClientAdapter` exists with full imports. `@Bean` gives explicit control over bean names, conditions, and dependencies.

### Use @Import When a Separate Configuration Class Is Needed

```java
@AutoConfiguration
@Import(VendorSupportConfiguration.class)
class VendorAutoConfiguration {
}
```

`VendorSupportConfiguration` is a hypothetical class in the snippet. `@Import` **explicitly states which supporting configurations** are applied rather than scanning the entire library namespace. When features depend on different classpaths, put dedicated conditions on supporting classes or nested configurations.

### Use @ConfigurationProperties When Configuration Parameters Exist

If the library needs timeouts, endpoints, or connection limits, declare a properties class with a dedicated prefix such as `acme.client` and register it via an appropriate mechanism, such as `@EnableConfigurationProperties(AcmeClientProperties.class)` on the auto-configuration. A properties class is configuration data, not a reason to open library-wide `@ComponentScan`.

Note that **`@ConfigurationPropertiesScan` is also a distinct scanning mechanism** with its own rules and scope; it does not replace the advice to separate auto-configuration from component scanning. Having a class configured via that annotation does not mean the auto-configuration should reside in the application package.

## 10. Verifying Exclusion Actually Works

Spring Boot allows excluding an auto-configuration class via:

```java
@SpringBootApplication(
    excludeName = "demo.autoconfig.GreetingAutoConfiguration"
)
public class DemoApplication {
}
```

This is an illustrative snippet, not a complete replacement for the `DemoApplication` run in section 6. The property equivalent is:

```properties
spring.autoconfigure.exclude=demo.autoconfig.GreetingAutoConfiguration
```

Effect: removes the named class from selected candidate auto-configurations. **Exclusion is not a command to delete all beans of the same type** and does not remove a bean declared by the application through another configuration path. That is why the example in section 6 still prints `custom` when an application-supplied bean exists.

If an auto-configuration class is still scanned as regular configuration due to a wrong package, merely adding `exclude` does not address the root cause. Fix the package layout and registration path first.

**Diagnosing with the Conditions Evaluation Report:**

```bash
java -jar target/greeting-autoconfig-scan-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none \
  --debug
```

Boot prints auto-configuration condition diagnostics. Look for `GreetingAutoConfiguration` under *Positive matches*, *Negative matches*, or *Exclusions* depending on the case. The condition report reveals why a candidate was or was not applied; if a bean definition exists yet instantiation fails, you still need to read the stack trace and root cause.

### Checklist When Reviewing a Starter

| Check | Expected state |
| --- | --- |
| Which package does the auto-configuration class reside in? | Separated from the default component-scan package tree of expected consuming apps |
| Does the JAR contain `AutoConfiguration.imports`? | Yes, with exact fully qualified class names |
| Does the auto-configuration use `@ComponentScan`? | Should be avoided; use explicit `@Import` or `@Bean` |
| Is `@ConditionalOnClass` used for optional dependencies? | Yes, if configuration depends on classes/libraries not always present |
| Do defaults have appropriate `@ConditionalOnMissingBean`? | Yes, if the API allows applications to replace the bean |
| Is the exclusion case tested? | Excluding drops the default configuration without reloading it via scan |
| Is a user-provided bean tested? | When configuration permits, the application bean wins per designed conditions |
| Is the root package accidentally scanned too broadly? | `scanBasePackages` scope includes only necessary application components |

## 11. Common Mistakes and Misconceptions

### Mistake 1: "Because it has @AutoConfiguration, Spring never scans that class"

False. `@AutoConfiguration` carries Spring configuration semantics, and if the class lies inside component-scanning scope, the scanner can still treat it as a configuration candidate. The annotation name is not a barrier against scanning.

### Mistake 2: "Just putting it in a different JAR is enough"

Insufficient. Component scanning can discover components from JARs on the classpath if their package falls inside the scan scope. Separation of **package** and scanner scope is the core issue.

### Mistake 3: "Having a .imports file means the class cannot be scanned"

False. `.imports` supplies the import path for Boot; it does not eliminate the possibility of the application accidentally scanning the class. You must organize packages so the class enters the application only via the intended path.

### Mistake 4: "Widen scanBasePackages to the highest package to stop missing beans"

Sometimes this causes the application to pick up unwanted components, including library auto-configurations. Check which source the missing bean belongs to first: component scan, explicit configuration, or auto-configuration.

### Mistake 5: "Auto-configuration should @ComponentScan the entire library to save code"

This goes against Spring Boot guidance for auto-configuration. Use explicit `@Import` or clearly conditioned `@Bean` methods.

### Mistake 6: "Excluding an auto-configuration also deletes beans I wrote myself"

No. Exclusion targets selected auto-configurations. A bean declared independently by an application's `@Configuration` remains present if its own conditions match.

### Mistake 7: "The default bean didn't appear because the auto-configuration package is outside scan"

If `.imports` and conditions are correct, being **outside scan is intentional**, not a bug. Check the class name in `.imports`, dependencies, exclusions, and the Conditions Evaluation Report.

### Mistake 8: "@ConditionalOnMissingBean always guarantees no conflicts ever occur"

The condition depends on bean definitions visible at evaluation time and specific type/name criteria. Do not use it casually to mask a broken package layout or place it on regular configurations assuming the exact same ordering as standard auto-configuration.

## 12. How to Apply This in Real Projects

When creating a starter for a new feature, a sound process is:

1. **Design the API first:** identify which public beans to provide and where users can override them.
2. **Choose a separate namespace:** e.g., `com.acme.lib.autoconfigure` for auto-configure, `com.acme.app` for the application.
3. **Create the `@AutoConfiguration` class:** place appropriate conditions on classpath, properties, beans, and application type.
4. **Declare the class in `.imports`:** verify the resource exists after packaging the JAR.
5. **Register helpers explicitly:** use `@Bean`, `@Import`, `@EnableConfigurationProperties`; avoid component scanning inside auto-configurations.
6. **Test with a consuming app:** verify an application with normal scan scope still loads the auto-configuration via metadata.
7. **Verify customization and exclusion:** user creates custom bean; default configuration backs off as designed; excluding the auto-configuration class leaves no leftover scan path.
8. **Inspect conditions and lifecycle:** when a bean is missing, distinguish candidate not found, condition did not match, or bean definition existed yet instantiation failed.

For applications not developing a starter, you do not need to create auto-configurations for every component. Business logic should use regular `@Service`, `@Component`, `@Repository`, and `@Configuration`. Auto-configuration is best suited for providing **conditional default integrations** across multiple applications or a reusable library.

## 13. Self-Check Questions

**1.** Why are `GreetingAutoConfiguration` and `demo.app` in the same JAR, yet `demo.app` does not auto-scan that class?

Because `demo.autoconfig` is a sibling package of `demo.app`, not a subpackage of `demo.app`. The JVM classpath and component-scanning scope are two separate concepts.

**2.** How is `GreetingAutoConfiguration` still loaded in the default run?

Because the fully qualified class name is listed in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`, from which Boot considers it via `@EnableAutoConfiguration`.

**3.** Why does excluding auto-configuration print `GREETING: missing` instead of failing startup?

`ApplicationRunner` receives `ObjectProvider<Greeting>` and handles the absent-bean case. No other auto-configuration class registers `Greeting` in the example.

**4.** If `GreetingAutoConfiguration` is moved to `demo.app.autoconfig`, is `.imports` still enough to guarantee loading along the right path?

No. The class could then be found by component scan as regular configuration. Keep the class outside scan scope and register it via `.imports`.

**5.** When a library has three helper configurations, should you use `@ComponentScan` from the auto-configuration or selective `@Import`?

Per Spring Boot guidance, use explicit `@Import` for supporting configuration classes combined with appropriate conditions; do not let auto-configuration arbitrarily scan the library package.

**6.** When the user declares `Greeting("custom")`, why does the default back off?

`@ConditionalOnMissingBean(Greeting.class)` on the default method matches only if no matching bean exists at evaluation time. Application configuration is processed so the custom bean is supplied before the default decision phase in the example.

**7.** Is `scanBasePackages` a tool to toggle auto-configuration on or off?

No. It controls component scanning; `@EnableAutoConfiguration`, `.imports`, conditions, and exclusions manage auto-configuration. Widening scan too far can even accidentally scan auto-configure classes.

## 14. References

- Spring Boot — Creating Your Own Auto-configuration, section *Locating Auto-configuration Candidates*: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot — Using the @SpringBootApplication Annotation: https://docs.spring.io/spring-boot/reference/using/using-the-springbootapplication-annotation.html
- Spring Boot — Auto-configuration and exclusions: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Framework — Classpath Scanning and Managed Components: https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html
- Spring Boot 3.3 — AutoConfiguration annotation API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html
