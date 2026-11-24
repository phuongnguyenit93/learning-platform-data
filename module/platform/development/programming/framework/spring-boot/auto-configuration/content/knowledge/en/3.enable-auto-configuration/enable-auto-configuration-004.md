# Distinguishing Auto-Configuration Packages from @ComponentScan Scope in Spring Boot

> **Objective:** Understand why an `@AutoConfiguration` class outside the application package can still be loaded, while a `@Component` class in the same location is not found by component scan. Identify three easily confused concepts: **packages containing auto-configuration classes**, **packages scanned by `@ComponentScan`**, and **Spring Boot's `AutoConfigurationPackages` list**. Examples use Java 17 and Spring Boot 3.5.7; the core principles apply to Spring Boot 3.x and modern versions.

## 1. Same Word "Package", Three Different Roles

Suppose an application has the following Java package structure:

```text
dev.demo
├── app
│   ├── DemoApplication.java            @SpringBootApplication
│   └── owned
│       └── OwnedService.java           @Service
├── infra
│   └── ExternalComponent.java          @Component
├── api
│   └── MessageSource.java              interface
└── autoconfigure
    └── MessageAutoConfiguration.java   @AutoConfiguration
```

**Three scopes to keep separate:**

1. **Component scan scope.** By default, `@SpringBootApplication` scans the package containing the application class and its subpackages. In the example that is `dev.demo.app`, so it finds `OwnedService`; it does not automatically scan `dev.demo.infra` or `dev.demo.autoconfigure`.
2. **Where auto-configuration classes live.** `MessageAutoConfiguration` is discovered through the **auto-configuration candidate list**, specifically the `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` metadata on the classpath/JAR. This mechanism **does not discover candidates by scanning application packages**.
3. **`AutoConfigurationPackages`.** This is the list of **default application base packages** that Boot registers so certain auto-configured features can reference them, typically for locating JPA entities or Spring Data repositories. The name is misleading: it is **not** a list of packages containing `@AutoConfiguration` classes for Boot to scan.

Sharing a similar package name does not merge these three mechanisms; they have separate registration paths and responsibilities.

| Question | Answering Mechanism |
| --- | --- |
| Does Spring automatically find `@Service` in `dev.demo.app.owned`? | `@ComponentScan` with base package `dev.demo.app`: **yes**. |
| Does Spring automatically find `@Component` in `dev.demo.infra`? | With the default scan above: **no**. |
| Does Boot consider `MessageAutoConfiguration` in `dev.demo.autoconfigure`? | **Possibly yes**, if the class is in `AutoConfiguration.imports`, auto-configuration is enabled, and it is not excluded; the package need not be in component scan. |
| Does Boot automatically treat every class in `dev.demo.autoconfigure` as auto-configuration? | **No**. Only classes in the candidate list, or loaded via another specific registration mechanism, are evaluated. |
| Does changing `scanBasePackages` automatically change the JPA entity/repository base package? | **No**; those scopes have their own mechanisms and usually reference `AutoConfigurationPackages`. |

## 2. Processing Flow at Application Startup

`@SpringBootApplication` combines three primary capabilities:

- `@SpringBootConfiguration`: marks the root configuration of the application.
- `@ComponentScan`: discovers components based on base packages and filters.
- `@EnableAutoConfiguration`: activates finding, filtering, and importing auto-configuration candidates.

This can be visualized as:

```text
DemoApplication (@SpringBootApplication)
    |
    +-- Component scan: dev.demo.app and subpackages
    |      |
    |      +-- OwnedService (@Service)                 -> bean created
    |      +-- ExternalComponent (in dev.demo.infra)   -> not found by scan
    |
    +-- EnableAutoConfiguration
           |
           +-- read AutoConfiguration.imports from JARs/classpath
           +-- find dev.demo.autoconfigure.MessageAutoConfiguration
           +-- evaluate conditions (class, bean, property, ...)
           +-- process eligible @Bean                  -> MessageSource bean created
```

All branches contribute bean definitions to the Spring context, yet they differ in **candidate list source** and **registration conditions**.

### Component Scan Selects *by Package*

A class annotated only with `@Component` that sits outside every scanned base package will not be found **via that scan**. If the bean is declared using `@Bean`, `@Import`, manual registration, or auto-configuration, it can still exist in the context. Therefore, "not scanned" does not imply "cannot be a bean".

### Auto-Configuration Selects *by Imports and Conditions*

Spring Boot locates `AutoConfiguration.imports` files on the classpath, collects configuration class names, then applies exclusions and evaluates conditions such as `@ConditionalOnClass`, `@ConditionalOnMissingBean`, and `@ConditionalOnProperty`. A candidate **that is listed** may still create no beans if its conditions do not match.

An auto-configuration should be placed in a clear library package, independent of the consuming application's scan packages. Boot's official guidance recommends **not putting auto-configuration classes into component scan**, and **not letting auto-configuration enable component scan itself to pull in more components**; instead declare specific beans or use intentional `@Import`.

## 3. Actual Scope of @ComponentScan

Place `DemoApplication` in `dev.demo.app`:

```java
package dev.demo.app;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

By default, Spring searches for classes with stereotypes such as `@Component`, `@Service`, `@Repository`, `@Controller`, `@RestController`, and `@Configuration` inside `dev.demo.app` and its subpackages. A package with the same character prefix but a different branch, such as `dev.demo.application`, is not a subpackage of `dev.demo.app`.

`@ComponentScan` also supports:

- `basePackages`: specifies package names as strings.
- `basePackageClasses`: references a class to determine the package containing it; safer for package renaming/refactoring.
- `includeFilters`, `excludeFilters`, `useDefaultFilters`: selects classes by annotation, class type, regex, or custom filters.

On `@SpringBootApplication`, the convenience attributes are `scanBasePackages`/`scanBasePackageClasses` and apply only to **component scan**. When specifying a new scope, list the application packages you want to keep as well; if you only add an external package and forget the application root, existing beans can disappear from the scan.

An example replacing the application annotation with:

```java
@SpringBootApplication(scanBasePackages = {
    "dev.demo.app",
    "dev.demo.infra"
})
```

will cause components in both branches to be scanned. This is an annotation replacement snippet, not a standalone Java file. It **does not mean** Spring Boot needs to scan `dev.demo.autoconfigure` to load auto-configuration.

## 4. Where Is Auto-Configuration Registered?

For Spring Boot 3.x, a JAR or module providing auto-configuration declares the file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Its content is **fully qualified class names**, one class per line, for example:

```text
dev.demo.autoconfigure.MessageAutoConfiguration
```

The corresponding class:

```java
package dev.demo.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class MessageAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MessageSource.class)
    MessageSource messageSource() {
        return () -> "from-auto";
    }
}
```

This is an illustrative structure; to compile, it requires `import dev.demo.api.MessageSource;` and the interface definition in the complete example below.

Relationships among concepts:

- The entry `dev.demo.autoconfigure.MessageAutoConfiguration` in the imports file **names the specific class** to evaluate. The package name here is part of the Java class identifier, not a base package for bulk class scanning.
- Merely placing `@AutoConfiguration` without **registering the candidate** via the imports file (or another intentional import mechanism) will not make Boot discover it automatically on the classpath.
- A library containing multiple auto-configurations can list multiple class names in the file, one per line. **There is no package wildcard** like `dev.demo.autoconfigure.*` to select all classes automatically.
- `@AutoConfiguration` is meta-annotated with `@Configuration`, yet proper auto-configuration must be activated through the auto-configuration candidate path rather than relying on component scanning.
- Spring Boot by default applies auto-configuration exclusion filters when scanning from `@SpringBootApplication`. Even so, placing auto-configuration packages into the scan scope is a design prone to cross-dependencies, especially with custom configurations and test slices; keep package spaces separate.

In real configurations, conditions determine applicability. For example, `@ConditionalOnClass(PartnerSdk.class)` allows the configuration only when the related dependency is present; `@ConditionalOnMissingBean(PartnerClient.class)` yields if the application has already defined a matching bean. Back-off occurs during bean definition evaluation, not because a package lies inside or outside component scan scope.

## 5. Runnable Example: Outside Component Scan Yet Still Having an Auto-Configured Bean

Create the following Java 17 Maven project to observe **both mechanisms at once**.

```text
package-scope-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/dev/demo/
    │   │   ├── api/MessageSource.java
    │   │   ├── app/DemoApplication.java
    │   │   ├── app/owned/OwnedService.java
    │   │   ├── infra/ExternalComponent.java
    │   │   └── autoconfigure/MessageAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/dev/demo/app/PackageScopeTest.java
```

### 5.1. Maven Dependencies

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>dev.demo</groupId>
    <artifactId>package-scope-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

No web starter or database is needed, because this lesson observes context mechanics.

### 5.2. An Interface for Auto-Configuration to Create a Bean

`src/main/java/dev/demo/api/MessageSource.java`:

```java
package dev.demo.api;

@FunctionalInterface
public interface MessageSource {
    String message();
}
```

The interface has no `@Component`; it only describes a dependency contract.

### 5.3. A Component Inside Scan Scope

`src/main/java/dev/demo/app/owned/OwnedService.java`:

```java
package dev.demo.app.owned;

import org.springframework.stereotype.Service;

@Service
public class OwnedService {
    public String name() {
        return "owned";
    }
}
```

### 5.4. A Component Outside Scan Scope

`src/main/java/dev/demo/infra/ExternalComponent.java`:

```java
package dev.demo.infra;

import org.springframework.stereotype.Component;

@Component
public class ExternalComponent {
    public String name() {
        return "external";
    }
}
```

Despite having `@Component`, this class is not inside `dev.demo.app` or its subpackages.

### 5.5. An Auto-Configuration Also Outside Scan Scope

`src/main/java/dev/demo/autoconfigure/MessageAutoConfiguration.java`:

```java
package dev.demo.autoconfigure;

import dev.demo.api.MessageSource;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(MessageSource.class)
public class MessageAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MessageSource.class)
    MessageSource messageSource() {
        return () -> "from-auto";
    }
}
```

Register the candidate in `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:

```text
dev.demo.autoconfigure.MessageAutoConfiguration
```

`MessageAutoConfiguration` **does not need to be inside `@ComponentScan`**. It will be evaluated by Spring Boot because it is declared in the imports file. `@ConditionalOnClass` matches because `MessageSource` exists in the project. If no other `MessageSource` bean exists, `@ConditionalOnMissingBean` matches and `messageSource` is registered.

### 5.6. Application to Observe Results

Replace `src/main/java/dev/demo/app/DemoApplication.java` with this complete file:

```java
package dev.demo.app;

import dev.demo.api.MessageSource;
import dev.demo.app.owned.OwnedService;
import dev.demo.infra.ExternalComponent;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                 SpringApplication.run(DemoApplication.class, args)) {
            System.out.println(
                "owned.count=" + context.getBeansOfType(OwnedService.class).size()
            );
            System.out.println(
                "external.count=" + context.getBeansOfType(ExternalComponent.class).size()
            );
            System.out.println(
                "message.count=" + context.getBeansOfType(MessageSource.class).size()
            );
            System.out.println(
                "message.value=" + context.getBean(MessageSource.class).message()
            );
        }
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn -q spring-boot:run
```

The four lines printed by the program (excluding startup logs):

```text
owned.count=1
external.count=0
message.count=1
message.value=from-auto
```

**Reading the output:**

1. `OwnedService` sits under `dev.demo.app`, so it is found by component scan.
2. `ExternalComponent` is marked `@Component` yet sits under `dev.demo.infra`, so it is not picked up by the default scan.
3. `MessageAutoConfiguration` sits under `dev.demo.autoconfigure`, also outside the scan scope, yet **is still loaded via the imports file**.
4. The `MessageSource` bean appears because the `@Bean` method in the auto-configuration satisfies its conditions.

A very important observation: **having `import dev.demo.infra.ExternalComponent;` in `DemoApplication` only tells the Java compiler about the class type**. Java `import` is not Spring `@Import`; it does not register beans.

### 5.7. Two Changes to Prove the Mechanism

**Experiment A — widen component scan:** Replace the `@SpringBootApplication` annotation with:

```java
@SpringBootApplication(scanBasePackages = {
    "dev.demo.app",
    "dev.demo.infra"
})
```

Then `external.count=1`; `owned.count=1` and `message.count=1` as before. You added a scan scope for components **without needing to change `AutoConfiguration.imports`**.

**Experiment B — exclude auto-configuration:** Restore the original annotation, then replace it with:

```java
@SpringBootApplication(
    exclude = dev.demo.autoconfigure.MessageAutoConfiguration.class
)
```

This is a replacement annotation snippet. Because `MessageSource` is no longer created, `context.getBean(MessageSource.class)` in the sample main will throw `NoSuchBeanDefinitionException`. If you want to run and observe the state after excluding, **replace the last print statement** with:

```java
System.out.println(
    "message.present=" + !context.getBeansOfType(MessageSource.class).isEmpty()
);
```

Relevant lines when running variant B:

```text
owned.count=1
external.count=0
message.count=0
message.present=false
```

The result proves that `exclude` affects candidate auto-configurations, while default component scanning remains independent.

**Further distinction:** If you only remove the class name from `AutoConfiguration.imports` and have no other import path, `MessageAutoConfiguration` is no longer an automatically discovered candidate for Boot; `@AutoConfiguration` standing alone does not make the class self-discoverable.

## 6. Testing Boundaries and Conditions with JUnit

Create `src/test/java/dev/demo/app/PackageScopeTest.java`:

```java
package dev.demo.app;

import dev.demo.api.MessageSource;
import dev.demo.app.owned.OwnedService;
import dev.demo.autoconfigure.MessageAutoConfiguration;
import dev.demo.infra.ExternalComponent;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = DemoApplication.class)
class PackageScopeTest {

    @Autowired
    ApplicationContext context;

    @Test
    void scanOnlyOwnsApplicationPackageButAutoConfigurationStillLoads() {
        assertThat(context.getBeansOfType(OwnedService.class)).hasSize(1);
        assertThat(context.getBeansOfType(ExternalComponent.class)).isEmpty();
        assertThat(context.getBeansOfType(MessageSource.class)).hasSize(1);
        assertThat(context.getBean(MessageSource.class).message())
            .isEqualTo("from-auto");
    }

    @Test
    void customMessageSourceMakesAutoConfigurationBackOff() {
        new ApplicationContextRunner()
            .withUserConfiguration(UserSourceConfiguration.class)
            .withConfiguration(
                AutoConfigurations.of(MessageAutoConfiguration.class)
            )
            .run(ctx -> {
                assertThat(ctx).hasSingleBean(MessageSource.class);
                assertThat(ctx).doesNotHaveBean("messageSource");
                assertThat(ctx.getBean(MessageSource.class).message())
                    .isEqualTo("from-user");
            });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserSourceConfiguration {
        @Bean
        MessageSource userMessageSource() {
            return () -> "from-user";
        }
    }
}
```

Run:

```bash
mvn -q test
```

The two tests guard two separate concepts:

- The integration test boots the real application and verifies that component scan only sees `OwnedService`, while imports still bring auto-configuration into the context.
- The `ApplicationContextRunner` test loads only the user configuration and the auto-configuration under test; seeing the `userMessageSource` bean, the default bean named `messageSource` backs off. **Back-off depends on bean conditions, not on which package holds the class.**

The first test applies to the **default configuration from step 5.6**; if you modified the annotation for experiment A or B, restore the original configuration before running the tests.

## 7. What Does "Auto-Configuration Package" Mean in the API?

The name `org.springframework.boot.autoconfigure.AutoConfigurationPackages` easily leads learners to think it refers to packages containing auto-configuration classes. In fact, this class stores **the application's base packages** for Boot features to reference. By convention, the package containing the `@EnableAutoConfiguration` class (usually the `@SpringBootApplication` class) is registered as the root.

For the sample application:

- `DemoApplication` is in `dev.demo.app`.
- Default component scan starts in `dev.demo.app`.
- Default `AutoConfigurationPackages` also contains `dev.demo.app` by convention.
- Auto-configuration class `MessageAutoConfiguration` is in `dev.demo.autoconfigure` and is loaded **via imports**, not because `AutoConfigurationPackages` contains `dev.demo.autoconfigure`.

The first two values match **under default configuration**, yet they belong to two different mechanisms; therefore they must not be conflated.

You can observe this in the sample application by adding inside the try-with-resources block in `main`:

```java
System.out.println(
    "auto.packages=" +
    org.springframework.boot.autoconfigure.AutoConfigurationPackages.get(
        context.getBeanFactory()
    )
);
```

With the root class in `dev.demo.app` and default configuration, the extra line printed is:

```text
auto.packages=[dev.demo.app]
```

`AutoConfigurationPackages.get(...)` takes a `BeanFactory` and reads the registered package metadata; it does not return the list of classes in `AutoConfiguration.imports`.

### Why Are JPA Entities and Spring Data Repositories Related?

Some auto-configurations use this base package list as the default scope for entities/repositories. In a Spring Boot application with JPA, placing the application class in the root package typically lets Spring find entities/repositories by convention. However:

- `@Entity` is not a regular component scan stereotype.
- Spring Data repository interfaces are handled by the repository scanning mechanism.
- Adding `scanBasePackages="dev.demo.infra"` to `@SpringBootApplication` **does not automatically** add `dev.demo.infra` to the `AutoConfigurationPackages` list.
- If entities/repositories live in another package, use appropriate configurations such as `@EntityScan` and `@EnableJpaRepositories` when truly needed, or reorganize the root package.

Do not use `@ComponentScan` to fix an entity scanning error without identifying the mechanism causing the failure.

## 8. Three Deployment Layouts and Outcomes

| Layout | Expected Outcome | Notes |
| --- | --- | --- |
| `@SpringBootApplication` at `com.acme.orders`; services under `com.acme.orders.domain` | Services are scanned | This is the standard and easiest-to-understand layout. |
| Library has `@AutoConfiguration` in `com.vendor.cache.autoconfigure`, listed in imports | Boot evaluates auto-configuration if dependencies are present and auto-configuration is enabled | No need to add `com.vendor.cache.autoconfigure` to `@ComponentScan`. |
| A `@Component` in `com.vendor.cache.internal`, application only scans `com.acme.orders` | Component is not scanned by default | A stereotyped class inside a dependency does not automatically become a bean. |
| Application sets only `scanBasePackages="com.vendor.cache.internal"` | Scan package changes; app components may disappear if app root is omitted | Always specify the complete set of packages to scan. |
| Application excludes `CacheAutoConfiguration` | That auto-configuration is removed from applied candidates | Component scan does not stop scanning application packages because of this. |
| Explicitly register `@Import(CustomCacheConfiguration.class)` | Only the imported configuration and its beans are processed | Useful when the application deliberately selects a specific configuration. |

### Recommended Organization

An application and an integrated starter can separate boundaries like this:

```text
com.acme.orders
├── OrdersApplication.java
├── domain/...
└── infrastructure/...

com.acme.shared.cache
├── CacheClient.java                 (API/service library)
└── autoconfigure/
    └── CacheAutoConfiguration.java (auto-configuration library)
```

For an organization's internal starter, `CacheAutoConfiguration` should be registered in the imports file inside the autoconfigure JAR. It can use `@ConditionalOnClass` and `@ConditionalOnMissingBean` so it does not impose an implementation when the application already provides its own bean. Do not tell applications to scan all of `com.acme.shared` as a mandatory condition for the library to work.

## 9. Common Mistakes and How to Diagnose Them

### Mistake 1: "I added the starter, yet the library's @Component bean did not appear"

**Possible cause:** the starter brought the JAR onto the classpath, yet the component lies outside the scan root and the library did not provide an auto-configuration registering that bean.

Check the JAR's imports file, `@AutoConfiguration` classes, and `@Bean` methods. If the library only expects manual configuration import, follow the library's guide; do not expand scan arbitrarily across all dependency packages.

### Mistake 2: "@AutoConfiguration is outside the main package so it did not run"

**This reasoning is incorrect.** Check:

1. Is the `AutoConfiguration.imports` file located properly under `META-INF/spring/` on the application classpath?
2. Does the fully-qualified name in the file match the compiled class name?
3. Is `@SpringBootApplication` or `@EnableAutoConfiguration` declared?
4. Is the auto-configuration class excluded?
5. Do `@ConditionalOnClass`, `@ConditionalOnProperty`, and `@ConditionalOnMissingBean` match?

The package location of the auto-configuration class is not the primary filter in this mechanism.

### Mistake 3: "@ComponentScan(basePackages = ...) is enough to change every search scope"

`@ComponentScan` can change component boundaries, yet it does not change the imports list, entity scanning, repository scanning, or `@ConfigurationPropertiesScan`. When an error occurs, identify **which kind of class** is missing: component, entity, repository interface, or auto-configuration.

### Mistake 4: "Put the autoconfigure package in scan to make sure it gets loaded"

This practice can create accidental dependencies, load at the wrong phase, or duplicate configuration registration when combined with manual imports. Spring Boot recommends registering auto-configurations via the candidate list and keeping them out of component scanning. Adding manual `@ComponentScan` onto the root configuration can also strip test-slice exclude filters provided by Boot meta-annotations.

### Mistake 5: "Changed scanBasePackages, yet JPA still cannot find entities"

Remember that `AutoConfigurationPackages` does not change automatically with `scanBasePackages`. Review the root class's package, `@EntityScan`, and `@EnableJpaRepositories` if needed. Also verify whether entity/repository creation is conditional on dependencies or properties.

### Mistake 6: "The auto-configured bean appeared, wait—the default bean did not appear"

That may be **proper back-off**. If `@ConditionalOnMissingBean(MessageSource.class)` sees a bean provided by the application, the default bean will not be registered. This differs from the auto-configuration **not being loaded**. Distinguish a negative condition match from an unregistered candidate.

### Useful Diagnostic Tools

Run the application with the flag:

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
```

The Condition Evaluation Report shows which auto-configurations had positive/negative matches and why. Additionally, inspect the build output after packaging:

```bash
mvn -q package
jar tf target/package-scope-demo-1.0.0.jar
```

Use `jar tf` to confirm the imports resource actually resides inside the JAR at the expected path (for example, Spring Boot executable JARs typically place application resources under `BOOT-INF/classes/`). Finding the imports file at the exact location in the JAR helps distinguish resource packaging errors from scan errors.

If Spring Boot Actuator is added, the conditions and beans endpoints are also helpful when properly exposed and secured; never open diagnostic endpoint access in production just for casual inspection.

## 10. Principles for Designing Modules

1. **Application actively owns its components:** place the `@SpringBootApplication` class in a root package containing most application components; expand scan only when genuine application package boundaries exist elsewhere.
2. **Library owns its auto-configuration:** declare auto-configurations with `@AutoConfiguration` and an imports file; classpath/property/bean conditions ensure configuration applies only where appropriate.
3. **Integration configs chosen manually:** use `@Import` when a specific configuration class needs to be included, rather than expanding scan indefinitely.
4. **Entities/repositories outside root:** handle with dedicated scanning mechanisms when needed, instead of assuming everything depends on `@ComponentScan`.
5. **Unexpected or missing bean:** identify the bean's registration source in the context, then read the Condition Evaluation Report and bean list; avoid guessing solely from package layout.

## 11. Comprehension Self-Check

1. `@SpringBootApplication` is in `com.demo.app`. Will a `@Service` in `com.demo.shared` appear automatically? **No** via default scan; it must sit within the scan tree or be registered by another mechanism.
2. `com.vendor.autoconfigure.FooAutoConfiguration` is outside the application package yet listed in `AutoConfiguration.imports`. Can it be evaluated? **Yes**, if auto-configuration is enabled and it is not excluded; its own conditions still decide whether beans are created.
3. Does an `@AutoConfiguration` class need `@ComponentScan` for Spring to find it? **No**. Best practice is to keep auto-configurations out of component scanning.
4. Does `@SpringBootApplication(scanBasePackages = "com.demo.shared")` still scan services in `com.demo.app`? **No**; you must declare the application root in the base packages set if you want to keep it.
5. Does `AutoConfigurationPackages.get(...)` return the list of every `@AutoConfiguration` class? **No**. It returns the registered base packages used for certain application defaults.
6. Does `scanBasePackages` automatically change the entity scanning scope? **No**; the two configuration mechanisms must be treated separately.
7. If an auto-configuration is loaded yet `@ConditionalOnMissingBean` does not match, what happens? **The corresponding default bean is not registered**; evaluating an auto-configuration and backing off are two different things.
8. When encountering a "missing bean" error, what should you check first? **The source of the bean definition** (component scan, import, bean method, auto-configuration), then packages, conditions, properties, and the corresponding condition logs.

## Official Resources for Further Reading

- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): how to declare imports, conditions, and the recommendation against scanning auto-configuration classes.
- [Spring Boot — Structuring Your Code](https://docs.spring.io/spring-boot/reference/using/structuring-your-code.html): placement of the main class and root package.
- [Spring Framework — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html): component scanning mechanics and filters.
- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html): activation, exclusions, and condition evaluation.
- [Spring Boot API — AutoConfigurationPackages](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/AutoConfigurationPackages.html): root package list used as defaults for features such as JPA entity scanning.
