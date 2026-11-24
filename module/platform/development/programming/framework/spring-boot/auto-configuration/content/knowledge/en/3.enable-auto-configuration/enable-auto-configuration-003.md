# The Role of @AutoConfigurationPackage and AutoConfigurationPackages

## 1. The Problem: Which Root Package Does Auto-Configuration Need to Know?

When starting a Spring Boot application, certain auto-configured features need a **starting point to locate application types**. For example, JPA configuration typically needs a default package to look for `@Entity` classes; Spring Data configuration may use a default package to locate repositories. These packages are called **auto-configuration packages**.

Two APIs in the `org.springframework.boot.autoconfigure` package are responsible for recording and providing this information:

- **`@AutoConfigurationPackage`:** annotation asking Spring Boot to **register one or more package names as base packages for auto-configured features**.
- **`AutoConfigurationPackages`:** utility/infrastructure class used to **store, look up, or register additional package lists** in the application's `BeanFactory`/`BeanDefinitionRegistry`.

Important: registering a package **does not mean immediately scanning every class in the package, creating beans, enabling every starter, or adding auto-configuration classes to the candidate list**. It supplies location metadata for *features that need it* to query and use according to their own rules.

~~~text
@SpringBootApplication
   |
   +-- @EnableAutoConfiguration
          |
          +-- @AutoConfigurationPackage
          |      |
          |      +-- @Import(AutoConfigurationPackages.Registrar)
          |             |
          |             +-- Store default package in BeanFactory
          |                   (usually the package of the application class)
          |
          +-- @Import(AutoConfigurationImportSelector)
                 |
                 +-- Select candidate auto-configuration classes
                     from AutoConfiguration.imports
                 +-- Apply exclusions and relevant conditions

An auto-configured feature needing a root package
   -> AutoConfigurationPackages.get(beanFactory)
   -> package names -> locate entities/repositories/... depending on feature
~~~

In the diagram, **the two branches under `@EnableAutoConfiguration` have different functions**: one branch registers package information; the other selects auto-configurations. This separation explains why changing the default package is not equivalent to changing the list of auto-configurations.

## 2. Why Does `@SpringBootApplication` Have a Default Package Automatically?

In Spring Boot 3.3, the annotations relate as follows:

~~~java
@SpringBootApplication
// equivalent in primary semantic roles:
// @SpringBootConfiguration
// @EnableAutoConfiguration
// @ComponentScan
~~~

`@EnableAutoConfiguration` itself is annotated with `@AutoConfigurationPackage` and `@Import(AutoConfigurationImportSelector.class)`. Therefore, when the main class is processed by Spring, Boot can register the package containing the class that enabled auto-configuration, while simultaneously running the auto-configuration selection mechanism.

Example:

~~~text
com.example.shop
├── ShopApplication.java   <- @SpringBootApplication
├── domain
│   └── Product.java       <- @Entity
├── repository
│   └── ProductRepository.java
└── service
    └── ProductService.java
~~~

With `ShopApplication` in package `com.example.shop`, the default auto-configuration package is normally `com.example.shop`. A feature that finds entities/repositories by default convention can treat this as the root to look for eligible types in subpackages.

**Signpost to remember:** the package of the class activating `@EnableAutoConfiguration` (usually the `@SpringBootApplication` class) carries special significance. This is why Spring Boot documentation recommends placing the startup class in a root package above application subpackages.

Do not conclude that simply having this package name makes JPA work: you still need dependencies, data configuration, required beans, and JPA configuration conditions. `@AutoConfigurationPackage` only helps specify *where to look*, not *which features are guaranteed to work*.

## 3. What Does `@AutoConfigurationPackage` Do Technically?

The annotation has a conceptual structure equivalent to:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Inherited
@Import(AutoConfigurationPackages.Registrar.class)
public @interface AutoConfigurationPackage {
    String[] basePackages() default {};
    Class<?>[] basePackageClasses() default {};
}
~~~

This is an **abbreviated structural excerpt for explanation**, not a class you need to define yourself. `@Import` brings Boot's internal registrar into the configuration processing pipeline. The registrar reads annotation metadata and registers the list of package names into the `AutoConfigurationPackages` infrastructure.

Rules for choosing package names:

1. If neither `basePackages` nor `basePackageClasses` is specified, the package of the **annotated class** is used as the package name.
2. If you want to specify a package explicitly, use `basePackages = "com.example.domain"`.
3. If you want greater safety when renaming packages during refactoring, use `basePackageClasses = DomainMarker.class`. Boot takes **the package containing the specified class**, without turning that class into a bean.

Illustrative example:

~~~java
import org.springframework.boot.autoconfigure.AutoConfigurationPackage;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@AutoConfigurationPackage(basePackages = "com.example.inventory.domain")
public class InventoryPackageConfiguration {
}
~~~

This is a **configuration snippet** that must be scanned/imported/registered to take effect; simply creating the class file without Spring processing it will not run the annotation. It registers the package name `com.example.inventory.domain` into the context's auto-configuration package set.

### `basePackages` and `basePackageClasses`

| Attribute | Usage | Characteristics |
| --- | --- | --- |
| `basePackages` | `@AutoConfigurationPackage(basePackages = "com.example.domain")` | Uses strings; must be updated when renaming packages |
| `basePackageClasses` | `@AutoConfigurationPackage(basePackageClasses = DomainMarker.class)` | Uses class/interface to resolve package by type, refactor-friendly |
| No attributes passed | `@AutoConfigurationPackage` | Uses the package of the annotated class |

A marker can be an empty interface:

~~~java
package com.example.domain;

// Used only for package reference, no bean needs to be created.
public interface DomainMarker {
}
~~~

Do not interpret `basePackageClasses = DomainMarker.class` as a command to register `DomainMarker` as a bean or to scan only this class. The API uses the marker's package location as metadata.

## 4. `AutoConfigurationPackages`: Where to Look Up the Package List

`AutoConfigurationPackages` is a Spring Boot utility class providing key static methods:

~~~java
public static boolean has(BeanFactory beanFactory);
public static List<String> get(BeanFactory beanFactory);
public static void register(
    BeanDefinitionRegistry registry, String... packageNames
);
~~~

*The above are API signatures for study, not a standalone compilable Java class.*

- `has(beanFactory)`: checks whether auto-configuration base packages are available in the bean factory.
- `get(beanFactory)`: retrieves the list of package names Boot has registered. **May throw `IllegalStateException`** if the package mechanism has not been set up; calling `has` first in code where the context is uncertain is good practice.
- `register(registry, packageNames...)`: programmatically registers packages. Subsequent registrations can append package names. This API is useful for infrastructure mechanisms, while application code should prefer annotations and conventions over manipulating the registry directly.

Example usage in a started Spring Boot context:

~~~java
import java.util.List;
import org.springframework.boot.autoconfigure.AutoConfigurationPackages;
import org.springframework.context.ConfigurableApplicationContext;

// context is a started ConfigurableApplicationContext.
boolean available = AutoConfigurationPackages.has(context.getBeanFactory());
if (available) {
    List<String> roots =
        AutoConfigurationPackages.get(context.getBeanFactory());
    System.out.println(roots);
}
~~~

This is a **snippet requiring a `context` variable**, not a standalone runnable Java file. `getBeanFactory()` returns `ConfigurableListableBeanFactory`, which matches the `BeanFactory` parameter of both methods above.

### What Is Stored?

Boot registers package information in the container, and interested auto-configurations can look it up at the appropriate stage. This is a **list of package names**, not a list of discovered classes, nor a list of `BeanDefinition`s corresponding to every class inside those packages.

For the same reason, `get(...)` returning `com.example.shop` **does not prove** how many entities, repositories, or services exist in that package. You must check each respective scanner/registry to know the actual outcome.

## 5. Distinguishing Three Frequently Confused Scopes

Spring Boot has multiple package-related mechanisms with different purposes.

| Mechanism | Question Answered | Who Uses It | Does It Create Beans from Every Class? |
| --- | --- | --- | --- |
| `@ComponentScan` / `scanBasePackages` | Which packages should be scanned for eligible components? | Spring component scanner | Only for classes matching scan rules, not every class |
| `@AutoConfigurationPackage` / `AutoConfigurationPackages` | What are the default root packages for auto-config features that look them up? | Boot features such as certain entity/repository scanners | No |
| `AutoConfiguration.imports` | Which auto-configuration classes can be considered? | Boot's auto-configuration selection mechanism | No; conditions still decide configurations/beans |

**Easy-to-confuse example:**

~~~java
@SpringBootApplication(scanBasePackages = "com.example.controllers")
public class ShopApplication {
}
~~~

Suppose `ShopApplication` sits in `com.example.boot`. `scanBasePackages` above **only changes the `@ComponentScan` scope**; it does not automatically move the default `AutoConfigurationPackages` package to `com.example.controllers`. Entity/repository scanners are not controlled by this parameter in the same way.

Conversely, if you additionally register `com.example.entities` via `@AutoConfigurationPackage`, Spring **does not automatically expand `@ComponentScan`** to find `@Service` or `@Controller` classes in `com.example.entities`.

### How Do `@EntityScan` and `@EnableJpaRepositories` Differ?

- `@EntityScan` defines the scanning scope for persistence types such as JPA entities for supported mechanisms. Once an explicit scope is declared, it can replace the default package convention for finding entities.
- `@EnableJpaRepositories` can explicitly declare repository scanning packages, following the Spring Data JPA mechanism.
- `@ComponentScan` scans Spring components such as `@Component`/`@Service`/`@Controller`; it is not a direct substitute for the two mechanisms above.
- `@AutoConfigurationPackage` registers **default** package data for certain auto-configured features to use; it does not guarantee overriding explicit choices and is not a "universal scan command for everything".

Therefore, when you encounter a case where a repository is discovered but an entity is not managed, check the **repository scan scope** and **entity scope** separately rather than only adjusting `scanBasePackages`.

## 6. Complete Example: Adding a Package Without Expanding Component Scan

This experiment uses **Java 17+**, **Spring Boot 3.3.13**, and **Maven 3.9+**. No database is needed. The goal is to inspect the package list in `AutoConfigurationPackages` directly and demonstrate that it is independent of component scanning.

### Project Layout

~~~text
package-demo/
├── pom.xml
└── src/main/java/
    └── com/example/
        ├── launch/
        │   └── DemoApplication.java
        ├── config/
        │   └── ExtraPackageConfiguration.java
        ├── domain/
        │   ├── DomainMarker.java
        │   └── HiddenProbe.java
        └── component/
            └── ScannedProbe.java
~~~

The startup class sits in `com.example.launch`. We intentionally place two `@Component` classes in different packages: one inside the component scan area, and one only inside the package added to the auto-configuration package list.

### 6.1. `pom.xml`

~~~xml
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
    <groupId>com.example</groupId>
    <artifactId>package-demo</artifactId>
    <version>1.0.0</version>
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
~~~

`spring-boot-starter` is enough to build an `ApplicationContext` and observe simple beans. The demo does not use JPA; adding a package here demonstrates metadata only and does not require adding entities.

### 6.2. `src/main/java/com/example/domain/DomainMarker.java`

~~~java
package com.example.domain;

public interface DomainMarker {
}
~~~

This marker identifies the `com.example.domain` package via a Java type, giving IDE refactoring support.

### 6.3. `src/main/java/com/example/domain/HiddenProbe.java`

~~~java
package com.example.domain;

import org.springframework.stereotype.Component;

@Component
public class HiddenProbe {
}
~~~

`HiddenProbe` is annotated with `@Component`, yet it will not be discovered by component scan from `com.example.component`. It does not become a bean merely because `com.example.domain` was added to `AutoConfigurationPackages`.

### 6.4. `src/main/java/com/example/component/ScannedProbe.java`

~~~java
package com.example.component;

import org.springframework.stereotype.Component;

@Component
public class ScannedProbe {
}
~~~

This is a component inside the area selected for scanning via `scanBasePackages`. If the scanner runs, the default bean name will be `scannedProbe`.

### 6.5. `src/main/java/com/example/config/ExtraPackageConfiguration.java`

~~~java
package com.example.config;

import com.example.domain.DomainMarker;
import org.springframework.boot.autoconfigure.AutoConfigurationPackage;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@AutoConfigurationPackage(basePackageClasses = DomainMarker.class)
public class ExtraPackageConfiguration {
}
~~~

Spring processes this configuration only when it is brought into the context. It additionally registers the package name `com.example.domain` via the `@AutoConfigurationPackage` registrar. **It does not declare `@ComponentScan`** and does not register `HiddenProbe` as a bean.

### 6.6. `src/main/java/com/example/launch/DemoApplication.java`

~~~java
package com.example.launch;

import com.example.config.ExtraPackageConfiguration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.AutoConfigurationPackages;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Import;

@SpringBootApplication(scanBasePackages = "com.example.component")
@Import(ExtraPackageConfiguration.class)
public class DemoApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                 SpringApplication.run(DemoApplication.class, args)) {

            boolean hasRoots =
                AutoConfigurationPackages.has(context.getBeanFactory());

            List<String> roots = new ArrayList<>(
                AutoConfigurationPackages.get(context.getBeanFactory())
            );
            Collections.sort(roots);

            System.out.println("hasAutoPackages=" + hasRoots);
            System.out.println("autoPackages=" + roots);
            System.out.println("scannedProbe=" +
                context.containsBean("scannedProbe"));
            System.out.println("hiddenProbe=" +
                context.containsBean("hiddenProbe"));
        }
    }
}
~~~

Two key choices on this class:

1. `@SpringBootApplication(scanBasePackages = "com.example.component")` explicitly specifies the package for **component scan**. This does not change the default package of the auto-configuration mechanism, which remains tied to `com.example.launch`.
2. `@Import(ExtraPackageConfiguration.class)` brings the additional configuration annotated with `@AutoConfigurationPackage(basePackageClasses = DomainMarker.class)` into processing. Consequently, the auto-configuration package list gains `com.example.domain`.

`Collections.sort(roots)` is used so the printed output is deterministic, because package registration order is not the focus being tested.

### 6.7. Running and Comparing Output

From the `package-demo` directory:

~~~bash
java -version
mvn -version
mvn -q spring-boot:run
~~~

The four lines printed by `System.out.println` in the example:

~~~text
hasAutoPackages=true
autoPackages=[com.example.domain, com.example.launch]
scannedProbe=true
hiddenProbe=false
~~~

Spring Boot may print an additional banner and logs. The four lines above show:

- `com.example.launch` is the default package, determined by `DemoApplication` activating `@EnableAutoConfiguration`.
- `com.example.domain` was added by `ExtraPackageConfiguration`.
- Bean `scannedProbe` is present because `com.example.component` was component-scanned.
- Bean `hiddenProbe` is **absent** because merely registering an auto-configuration package does not cause the component scanner to scan that package.

**This observation checks the API and beans in the context directly**, without guessing from annotation names.

## 7. Three Small Changes to Test the Mechanism Yourself

### Trial 1: Remove `@Import(ExtraPackageConfiguration.class)`

In `DemoApplication`, remove the `@Import(ExtraPackageConfiguration.class)` annotation while keeping the other files unchanged. Because `com.example.config` is outside the component scan area, the extra configuration is not loaded. Expected output:

~~~text
hasAutoPackages=true
autoPackages=[com.example.launch]
scannedProbe=true
hiddenProbe=false
~~~

Explanation: `@EnableAutoConfiguration` is still present through `@SpringBootApplication`, so the default package remains. The extra `com.example.domain` disappears because its registrar never ran.

### Trial 2: Move Component Scan to the Domain Package

Restore `@Import` and then change `DemoApplication`:

~~~java
@SpringBootApplication(scanBasePackages = "com.example.domain")
@Import(ExtraPackageConfiguration.class)
public class DemoApplication {
    // Keep the main method from section 6.6 unchanged.
}
~~~

This is a **replacement snippet for the class declaration**, not a separate program. When rerun, expected output:

~~~text
hasAutoPackages=true
autoPackages=[com.example.domain, com.example.launch]
scannedProbe=false
hiddenProbe=true
~~~

The list of auto-configuration packages **stays the same**; only the component scan area changed. This case proves the two mechanisms are independent at the default configuration level.

### Trial 3: Remove `@AutoConfigurationPackage` from the Extra Configuration

Restore component scan to the original; keep `@Import(ExtraPackageConfiguration.class)`, but remove `@AutoConfigurationPackage(basePackageClasses = DomainMarker.class)` from the extra configuration class. The configuration class is still imported; it simply loses its new package registration effect. The output returns to:

~~~text
hasAutoPackages=true
autoPackages=[com.example.launch]
scannedProbe=true
hiddenProbe=false
~~~

You could still add a bean via `@Bean` inside `ExtraPackageConfiguration`: that bean would still be registered even without `@AutoConfigurationPackage`. This clearly separates **bringing a configuration into the context** from **registering a package for scanners that need it**.

## 8. When JPA or Spring Data Actually Uses These Packages

In the experiment above, `AutoConfigurationPackages.get(...)` returned two package strings, yet without persistence dependencies there was no entity/repository lookup. In an application with JPA/Spring Data, certain auto-configurations use these package names as the default source for finding specific types.

Suppose a project is organized as:

~~~text
com.acme.launch
  └── MainApplication.java
com.acme.catalog.domain
  └── Product.java          (@Entity)
com.acme.catalog.repo
  └── ProductRepository.java (Spring Data repository interface)
~~~

If the main class resides in `com.acme.launch`, the `com.acme.catalog.domain` and `com.acme.catalog.repo` packages lie **outside** the default package path. Several options exist depending on your goal:

**Option A: place the startup class in a shared parent package.** For example, move the application into `com.acme`, if the structure and scan scope fit. This is the convention-based approach Spring Boot encourages.

**Option B: register an additional auto-configuration package.** Use an imported configuration with `@AutoConfigurationPackage(basePackageClasses = CatalogMarker.class)`, where the marker sits in the root package `com.acme.catalog`. Features relying on `AutoConfigurationPackages` can see that additional default path.

**Option C: configure each scanner explicitly.** For JPA, use `@EntityScan(basePackageClasses = Product.class)`; for Spring Data JPA, when repository scope control is needed, use `@EnableJpaRepositories(basePackageClasses = ProductRepository.class)`. These two annotations target two different mechanisms. Once specific scopes are declared, check each scanner's rules rather than assuming everything inherits `AutoConfigurationPackages`.

Note: `@AutoConfigurationPackage` is not designed to replace all explicit scanning annotations. In multi-module systems with complex topologies, which option fits depends on the persistence mechanism used and the degree of explicit control you want.

### Why Can Repositories and Entities Differ?

The Spring Data repository scanner looks for **eligible repository interfaces**; the JPA entity scanner looks for **managed entity types**. Just because both can start from a similar root package does not mean they are a single scanner. If a repository bean exists yet a "Not a managed type" error occurs, inspect the managed entity set separately. If the entity exists yet the repository bean is missing, check repository enabling/scanning and auto-configuration conditions.

Do not assert which entities are managed solely via `AutoConfigurationPackages.get(...)`. Results must be verified via the JPA metamodel/`EntityManagerFactory` if using JPA.

## 9. What This Annotation Does NOT Do

1. **Does not add candidates to `AutoConfiguration.imports`.** Boot 3.x's auto-configuration class list comes from the `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` resource; base packages are not the mechanism for listing those classes.
2. **Does not enable/disable individual auto-configurations.** Configuration selection depends on exclusions, classpath, and conditions like `@ConditionalOnClass`, `@ConditionalOnProperty`, or `@ConditionalOnMissingBean`. Changing the auto-configuration package list does not directly alter those conditions.
3. **Does not perform component scanning.** A `@Service` class in a registered package can still fail to become a bean if it is outside the corresponding scan/import/registration scope.
4. **Does not automatically turn `@Entity` classes into regular Spring beans.** Entities are managed by JPA via persistence mechanisms; do not equate entities with `@Component` beans.
5. **Does not alter the search path of every library.** Each library decides how to locate its classes; only mechanisms designed to read `AutoConfigurationPackages` use this value.
6. **Does not guarantee runtime dependencies.** Registering a package name does not create a database, datasource, driver, or transaction manager.

### Two Misleading Names

- `@AutoConfigurationPackage` contains "AutoConfiguration", yet it works with the **application's base packages** used by auto-configured features. It is not used to declare a new `@AutoConfiguration` class.
- `AutoConfigurationPackages` contains "Packages", yet it is not a list of packages inside Spring Boot's auto-configuration JARs. The package names in the list are the **application's** search roots, registered by application configuration.

## 10. Diagnosing "Entity/Repository/Service Not Found"

A systematic checklist:

| Step | Question | Evidence to Collect |
| --- | --- | --- |
| 1 | Which package are the startup class and `@EnableAutoConfiguration` in? | Actual package path of the main class |
| 2 | What is the current auto-config base packages list? | `AutoConfigurationPackages.has/get` on the bean factory |
| 3 | Did anything register extra packages via `@AutoConfigurationPackage`? | Scanned/imported configuration classes and referenced markers |
| 4 | Is the failing mechanism component scan, JPA entity scan, or repository scan? | Annotation type and error message |
| 5 | Are `@EntityScan`/`@EnableJpaRepositories` or similar explicit configs present? | Annotations and actual configuration of each scanner |
| 6 | Did the relevant auto-configuration run and pass conditions? | Condition Evaluation Report via `--debug` or Actuator conditions |
| 7 | Does the target object/definition actually exist? | `ApplicationContext`, repository registry, or JPA metamodel |

Safe package verification snippet:

~~~java
var factory = context.getBeanFactory();
if (AutoConfigurationPackages.has(factory)) {
    System.out.println(
        AutoConfigurationPackages.get(factory)
    );
} else {
    System.out.println("No auto-configuration packages yet");
}
~~~

*The snippet above requires a `context` variable and appropriate imports.* Checking with `has` first avoids calling `get` in a context where no packages have been registered.

### Do Not Fix the Wrong Scope

If a `@Service` is missing, the first step is to check `@ComponentScan`, `@Import`, `@Bean`, and bean conditions. Adding `@AutoConfigurationPackage` will likely resolve nothing.

If an `@Entity` is missing, check whether JPA is enabled, persistence dependencies, default entity packages, `@EntityScan`, and metamodel messages. Expanding `scanBasePackages` only solves component scanning, not a replacement for `@EntityScan`.

If a repository is missing, check Spring Data dependencies, repository scanning mechanisms, and the package containing the interface. Avoid concluding solely from the interface class existing on the classpath.

## 11. Design Perspective: When Should You Declare Additional Packages?

**Prefer convention when the structure is simple.** Placing the `@SpringBootApplication` class in a common parent package gives both component scan and default auto-configurations a sensible scope. Do not use `@AutoConfigurationPackage` to mask an awkward package structure when a cleaner package architecture can be arranged.

**Prefer marker classes over strings when extended configuration is needed.** A `CatalogMarker` placed in the root package makes refactoring safe; no instance or bean needs to be created for the marker.

**Add packages only when there is an actual consumer.** If the application does not use any feature that reads `AutoConfigurationPackages`, adding a package only changes metadata. When using multiple persistence libraries, check each library's documentation because not every scanner uses the same default list.

**Keep the scope as narrow as needed.** Do not register overly broad packages such as `com` or the default package (unnamed package). Overly broad scopes can cause scanners to traverse many unrelated classes, increasing startup cost or triggering unintended discovery depending on the scanner.

**Do not call `AutoConfigurationPackages.register(...)` in business code.** This API is meant for infrastructure registration; the common approach for applications is annotations or sensible package layout. If programmatic intervention is necessary, you must understand `BeanDefinition` registration timing before consumers read the list.

## 12. Knowledge Self-Check

1. In the `@EnableAutoConfiguration` diagram, how do the `@AutoConfigurationPackage` registrar and `AutoConfigurationImportSelector` differ in their output?
2. `@SpringBootApplication(scanBasePackages = "com.example.feature")` is placed on a class in `com.example.launch`: without extra configuration, which package does `AutoConfigurationPackages.get(...)` normally return? Why?
3. If you register `com.example.domain` via `@AutoConfigurationPackage`, why might a `@Component` in that package still be absent from the context?
4. Does `basePackageClasses = CatalogMarker.class` record the package or an instance of the marker? When renaming a package, what advantage does this approach have?
5. When `AutoConfigurationPackages.has(beanFactory)` returns `false`, should you call `get(beanFactory)`? What behavior does the API specify if it has not been set up?
6. A repository is discovered but an entity is not managed: which scanners and dependencies should you inspect first?
7. In the section 6 example, predict the output when (a) removing `@Import`; (b) changing `scanBasePackages`; (c) removing `@AutoConfigurationPackage`. Explain each outcome by a specific mechanism.

**Completion criteria:** you can distinguish package metadata from component scan and import candidates; read root packages from `AutoConfigurationPackages`; know when to use `@AutoConfigurationPackage` versus `@EntityScan`/repository scanning; and explain the experiment's results through the relationship among annotations, registrars, and context.

## 13. Reference Documentation

- [Spring Boot 3.3.13 — `@EnableAutoConfiguration` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/EnableAutoConfiguration.html)
- [Spring Boot 3.3.13 — `@AutoConfigurationPackage` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationPackage.html)
- [Spring Boot 3.3.13 — `AutoConfigurationPackages` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationPackages.html)
- [Spring Boot 3.3.13 — `@SpringBootApplication` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/SpringBootApplication.html)
- [Spring Boot — Auto-configuration packages](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html#using.auto-configuration.auto-configuration-packages)
