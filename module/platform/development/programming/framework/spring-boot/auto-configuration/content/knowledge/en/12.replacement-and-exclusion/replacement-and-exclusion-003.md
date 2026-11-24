# exclude on @SpringBootApplication and @EnableAutoConfiguration

> **Spring Boot Auto Configuration → Replacement and Exclusion.** This lesson explains how to exclude a specific auto-configuration from Spring Boot's auto-configuration mechanism, compares `@SpringBootApplication` with `@EnableAutoConfiguration`, distinguishes `exclude` from `excludeName`, provides hands-on practice with Java 17 + Spring Boot 3.3, and inspects impacts on beans, dependencies, and application-defined configurations.

## 1. Problem: Spring Boot can auto-configure things the application does not need

When certain libraries are on the classpath, Spring Boot discovers matching *auto-configuration* classes and evaluates conditions such as `@ConditionalOnClass`, `@ConditionalOnBean`, or `@ConditionalOnMissingBean`. For instance, when an application has JDBC libraries and a database driver, Spring Boot can auto-configure a `DataSource`. This is helpful when the application uses a database, but may be unwanted in a service that does not access a database at all.

If a particular auto-configuration **does not fit the application's architecture**, Spring Boot lets you declare its exclusion:

~~~java
@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
public class Application {
}
~~~

Meaning: when Spring Boot selects the list of auto-configurations to apply, it will **not apply the `DataSourceAutoConfiguration` class through the normal auto-configuration mechanism**. That is different from removing JDBC libraries from the classpath, deleting every `DataSource` bean, or disabling everything related to databases.

**Question to ask before excluding:** does that configuration truly not belong in the application, or is it failing because required configuration is missing? Exclude is an architectural decision with a clear scope; it is not a trick to silence every startup error.

## 2. Relationship between the two annotations

### 2.1. What does @SpringBootApplication actually include?

In Spring Boot 3.x, `@SpringBootApplication` is a convenience annotation combining three roles:

~~~text
@SpringBootApplication
  ├── @SpringBootConfiguration  (a form of @Configuration)
  ├── @EnableAutoConfiguration  (enables auto-configuration)
  └── @ComponentScan           (scans components by package)
~~~

Because it already includes `@EnableAutoConfiguration`, using `@SpringBootApplication` also activates auto-configuration. Spring Boot provides two attributes directly on `@SpringBootApplication`:

- `exclude`: array of **auto-configuration classes** to skip.
- `excludeName`: array of **fully qualified string names** of auto-configuration classes to skip.

These two attributes use `@AliasFor` to forward to the underlying `@EnableAutoConfiguration` mechanism. Therefore, you can configure exclusions directly on the main application class without adding a separate `@EnableAutoConfiguration` annotation.

Example:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;

@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
public class DemoApplication {
}
~~~

This is an illustrative **declaration snippet**. A runnable application also needs `main` calling `SpringApplication.run(...)` and the corresponding dependencies; Section 5 provides the full program.

### 2.2. When to use @EnableAutoConfiguration?

If a project does not want all the features bundled by `@SpringBootApplication`, it can organize configuration manually and enable auto-configuration with `@EnableAutoConfiguration`:

~~~java
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableAutoConfiguration(exclude = DataSourceAutoConfiguration.class)
public class ManualApplicationConfiguration {
}
~~~

The class above is a **configuration component**; it does not automatically perform component scanning unless you add `@ComponentScan` or a dedicated registration mechanism. `@EnableAutoConfiguration` primarily enables auto-configuration selection and provides `exclude` and `excludeName` as shown above.

**Note:** if you already use `@SpringBootApplication`, there is no need to place `@EnableAutoConfiguration` on the same application class. Adding both does not enable auto-configuration "more strongly" and makes exclusion declarations harder to manage. For a standard Boot application, putting `exclude` directly on `@SpringBootApplication` is clearest.

### 2.3. Quick comparison

| Criterion | `@SpringBootApplication(exclude=...)` | `@EnableAutoConfiguration(exclude=...)` |
| --- | --- | --- |
| Purpose | Configure a Spring Boot application with component scan and auto-configuration | Enable auto-configuration on a manually organized configuration |
| Has `exclude` / `excludeName`? | Yes | Yes |
| Automatically component scans? | Yes, via `@ComponentScan` | No; declare separately if scanning is needed |
| Are they complete substitutes for each other? | No; `@SpringBootApplication` includes additional roles | Only responsible for the auto-configuration part |
| Auto-config exclusion effect | Same mechanism via alias | Direct declaration |
| When to use | Standard application class | Custom context startup or controlled modular configuration |

## 3. exclude: specifying the auto-configuration class with a Class literal

Syntax:

~~~java
@SpringBootApplication(
    exclude = {DataSourceAutoConfiguration.class}
)
public class DemoApplication {
}
~~~

When there is only one class, the curly braces can be omitted:

~~~java
@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
~~~

`exclude` has type `Class<?>[]`. Spring Boot uses the **specified auto-configuration class** to remove it from the applied candidates. For classes available on the compile classpath, this approach is checked by the compiler for package and type names, reducing the risk of typos.

For example, `DataSourceAutoConfiguration` in **Spring Boot 3.3** has the full name:

~~~text
org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

In Java source using Boot 3.3, the exact import is:

~~~java
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
~~~

**A note on versions:** auto-configuration packages can change between major Spring Boot generations. For example, some classes moved in Spring Boot 4.x. Always consult the Javadoc for your project's exact version instead of copying an import from another version.

### 3.1. Excluding multiple auto-configurations

Multiple classes can be declared using an array:

~~~java
@SpringBootApplication(
    exclude = {
        DataSourceAutoConfiguration.class,
        DataSourceTransactionManagerAutoConfiguration.class
    }
)
~~~

This is an **annotation snippet**, not a standalone program. When using Spring Boot 3.3, the second class is also in package `org.springframework.boot.autoconfigure.jdbc`; the proper import must be added. Only exclude each auto-configuration after confirming it is unsuitable; do not blindly exclude a long list without understanding the chain of effects.

### 3.2. Why must you exclude a true auto-configuration class?

Incorrect target example:

~~~java
// DO NOT use this to exclude an application-defined @Service:
@SpringBootApplication(exclude = MyPaymentService.class)
~~~

`MyPaymentService` is a regular component, not an auto-configuration candidate selected by Boot. Exclusion is not a mechanism for dropping arbitrary beans; if an invalid class is supplied, Boot may reject the exclusion configuration.

To control component scanning of an application-owned bean, see `@ComponentScan(excludeFilters=...)` or suitable conditions on that bean. To control the auto-configuration registration of **an auto-configuration class**, use `exclude`.

## 4. excludeName: specifying the class name as a string

When you do not want or cannot reference the class directly at compile time, use `excludeName`:

~~~java
@SpringBootApplication(
    excludeName =
        "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
)
public class DemoApplication {
}
~~~

The type of `excludeName` is `String[]`. The string must be a **fully qualified class name** (package + class name); writing only `"DataSourceAutoConfiguration"` will not suffice.

Equivalent approach when organizing configuration manually:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableAutoConfiguration(
    excludeName =
        "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
)
public class ManualConfiguration {
}
~~~

`excludeName` is useful for optional modules/integrations: the source code does not need to import that class. However, because the name is a string, the Java compiler **does not verify spelling**, so tests and checking the actual auto-configuration list are necessary.

### 4.1. Choosing exclude or excludeName?

| Scenario | Usually appropriate choice | Reason |
| --- | --- | --- |
| Auto-configuration class is present at compile time | `exclude = SomeAutoConfiguration.class` | Clear, refactoring-friendly, and class name is compiler-checked |
| Class belongs to an optional integration, no compile dependency | `excludeName = "com.vendor...AutoConfiguration"` | Avoids source dependency on an optional class |
| Exclusion needs to vary by deployment environment | `spring.autoconfigure.exclude` | Can be changed via externalized configuration outside code |
| Need to disable an application-defined bean | Do not use these two attributes | Adjust bean registration, conditions, or component scanning |
| Feature is already guarded by `@ConditionalOnClass` and class is absent | Usually no need to exclude | Auto-config already skips itself when conditions are unmet |

Both `exclude` and `excludeName` can be declared together if there are multiple items to exclude and each approach suits one group. Keep the exclusion set clearly managed and avoid pointless duplication.

## 5. Lab Spring Boot 3.3 + Java 17: excluding DataSourceAutoConfiguration

The lab below demonstrates how `exclude` affects **beans created by auto-configuration**. We intentionally add JDBC and H2 so Boot has all the conditions to create a `DataSource`; then we disable its specific auto-configuration and compare the results. No external database connection is required.

### 5.1. Project structure

~~~text
exclude-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── demo/
    │           └── exclude/
    │               └── ExcludeDemoApplication.java
    └── test/
        └── java/
            └── demo/
                └── exclude/
                    └── ExcludeDemoApplicationTest.java
~~~

Requires **JDK 17+**, **Maven**, and ability to download dependencies. For reproducible results, the snippets use Spring Boot **3.3.13**; the class imports here are for Boot 3.3.

### 5.2. pom.xml

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

    <groupId>demo</groupId>
    <artifactId>exclude-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
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
~~~

`spring-boot-starter-jdbc` provides JDBC/pool infrastructure; H2 allows Boot to pick an embedded database. When not excluded and without a manually declared `DataSource`, `DataSourceAutoConfiguration` can create a matching bean. This gives us a clear control baseline.

### 5.3. ExcludeDemoApplication.java — approach 1 with @SpringBootApplication

~~~java
package demo.exclude;

import javax.sql.DataSource;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
public class ExcludeDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ExcludeDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner report(ApplicationContext context) {
        return args -> {
            String[] names = context.getBeanNamesForType(DataSource.class);
            System.out.println("dataSource bean count: " + names.length);
        };
    }
}
~~~

This is a **complete program** inside the Maven project above. `ApplicationRunner` runs after the context starts; the code queries the container for how many beans of type `DataSource` exist, without executing SQL or making network connections.

### 5.4. Packaging and running with exclude

From the `exclude-demo` directory:

~~~bash
mvn -q -DskipTests package
java -jar target/exclude-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Business stdout printed by the program:

~~~text
dataSource bean count: 0
~~~

**Explanation:** `DataSourceAutoConfiguration` is removed from the auto-configuration list. The lab does not register another `DataSource`, so the container has no bean of that type. If extra Maven or library lines appear in your own environment, compare **the line printed by `System.out.println`**, rather than assuming all logs will be identical.

### 5.5. Control comparison: remove exclude and run again

In the **same file** `ExcludeDemoApplication.java`, replace:

~~~java
@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
~~~

with:

~~~java
@SpringBootApplication
~~~

Do not modify the reporting code. **Repackage** and run:

~~~bash
mvn -q -DskipTests package
java -jar target/exclude-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Expected output line in the demo environment with the JDBC starter and H2:

~~~text
dataSource bean count: 1
~~~

**Meaning:** when conditions are met, `DataSourceAutoConfiguration` allows default configuration to create a `DataSource`. Exclude prevents applying this configuration via auto-selection; when exclude is removed, the sample application gets the default bean back. The difference comes from **the auto-configuration application decision**, not from changing the classpath.

### 5.6. Approach 2: using @EnableAutoConfiguration instead of @SpringBootApplication

Replace the **entire** `ExcludeDemoApplication.java` file with the version below; **do not save both versions at once**:

~~~java
package demo.exclude;

import javax.sql.DataSource;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableAutoConfiguration(exclude = DataSourceAutoConfiguration.class)
public class ExcludeDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ExcludeDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner report(ApplicationContext context) {
        return args -> System.out.println(
                "dataSource bean count: " +
                context.getBeanNamesForType(DataSource.class).length
        );
    }
}
~~~

Continue:

~~~bash
mvn -q -DskipTests package
java -jar target/exclude-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Line printed by the program:

~~~text
dataSource bean count: 0
~~~

This version **has no `@ComponentScan`**, yet the lab still runs: the `report` bean is declared directly on the configuration class passed to `SpringApplication.run(...)`, while other auto-configurations are enabled thanks to `@EnableAutoConfiguration`. In an application that needs to find components across packages, you must add `@ComponentScan` or an appropriate import mechanism. This is a **difference in configuration organization**, not a difference in `exclude` effectiveness.

### 5.7. Approach 3: using excludeName

Going back to the `@SpringBootApplication` version, you can replace the annotation line with:

~~~java
@SpringBootApplication(
    excludeName =
        "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
)
~~~

Or in the version using `@EnableAutoConfiguration`:

~~~java
@EnableAutoConfiguration(
    excludeName =
        "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
)
~~~

These two snippets are **replacement annotations**, not standalone Java classes. With the right FQCN in Boot 3.3, the result will match `exclude = DataSourceAutoConfiguration.class`. Using a string avoids importing the excluded class in source code.

## 6. What does exclude actually change inside Spring Boot?

Conceptually, auto-configuration proceeds as follows:

~~~text
Classpath + AutoConfiguration.imports
               |
               v
   Candidate auto-configuration set
               |
               v
    Apply declared exclusions
     - @SpringBootApplication.exclude / excludeName
     - @EnableAutoConfiguration.exclude / excludeName
     - spring.autoconfigure.exclude
               |
               v
   Order and evaluate conditions
               |
               v
    Register matching bean definitions
               |
               v
       Instantiate bean instances
~~~

This is a simplified model to explain the **practical effect**: exclusions are applied to the candidate auto-configuration list, so an excluded configuration **does not proceed to register its default beans via auto-configuration**.

Do not confuse it with:
- Maven/Gradle **dependency resolution**: changing `exclude` in an annotation **does not remove JARs** from the application.
- **Component scan**: a regular `@Component` / `@Service` bean can still be discovered.
- **Manually registered application configuration**: a bean declared via `@Bean` can still exist, even if a corresponding auto-configuration was excluded.
- **Conditions of other auto-configurations**: other auto-configurations are still evaluated against the classpath, properties, and existing beans.
- **Instantiation ordering**: `exclude` removes a configuration from selection; it is not a tool for ordering object creation.

In Spring Boot's codebase, auto-configuration classes provide conveniences, and many beans are only created if no matching bean exists yet, such as via `@ConditionalOnMissingBean`. Exclude is for cases where you **want to disable an entire specific auto-configuration**, whereas overriding a bean or toggling a feature via properties may yield a lighter-weight outcome.

## 7. Exclude does not mean "never have a bean of that type"

Look at the component example below, applied to an application with JDBC libraries. It illustrates a bean **explicitly declared** by the application:

~~~java
@Configuration(proxyBeanMethods = false)
class ManualDataSourceConfiguration {

    @Bean
    DataSource dataSource() {
        return new org.springframework.jdbc.datasource
                .DriverManagerDataSource(
                    "jdbc:h2:mem:manual",
                    "sa",
                    ""
                );
    }
}
~~~

This is a **component snippet**; it needs imports for `@Configuration`, `@Bean`, `javax.sql.DataSource`, and must be component-scanned or imported. Place this configuration in a scanned package while also using:

~~~java
@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
~~~

In that case, the application **can still have a `DataSource`**, because the bean was created by manual configuration. Exclude only prevents `DataSourceAutoConfiguration` from applying automatically; it does not block all ways of registering a bean of the same type.

Similarly, excluding `SecurityAutoConfiguration` does not guarantee all security disappears; excluding a web configuration does not remove controllers written by the application. **The excluded class name and the bean's origin must be examined together.**

## 8. Externalized configuration option: spring.autoconfigure.exclude

Besides the two annotations, Spring Boot lets you declare a list of excluded auto-configuration classes via the `spring.autoconfigure.exclude` property.

**application.properties:**

~~~properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

**application.yml:**

~~~yaml
spring:
  autoconfigure:
    exclude:
      - org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

**Command-line argument:**

~~~bash
java -jar app.jar --spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

The property is useful when you want to adjust per environment without modifying source annotations. Exclusions can exist in both annotations and properties; Spring Boot collects the exclusions to apply from supported places.

**Design difference:** if an integration library is **never appropriate** for the module, declaring the exclusion on the application class clearly expresses intent. If the feature depends on the environment, the property can offer more flexible management. However, changes across profiles, CI/CD, and production environments must be managed carefully to avoid accidentally removing a required component.

Remember: the exclusion property takes **fully qualified class names**, not bean names, Maven artifacts, or guessed flags like `spring.datasource.enabled=false`.

## 9. When to exclude, and when to use another solution?

| Goal | Approach | Explanation |
| --- | --- | --- |
| Application has no need at all for an auto-configuration while the related library remains on the classpath | `exclude` / `excludeName` | Explicitly excludes that auto-configuration |
| Want to replace a default bean with an application-supplied bean | Create a matching `@Bean`, check `@ConditionalOnMissingBean` | Many auto-configs back off automatically when a user bean exists; exclude may be unnecessary |
| Optional feature has a dedicated property to enable/disable | Use the property supported by auto-config | Preserves standard starter mechanics, easier to operate |
| Want to avoid loading a library at runtime | Edit Gradle/Maven dependencies and packaging | Annotation exclude does not remove artifacts |
| Want to drop a self-declared `@Service` from scanning | Adjust `@ComponentScan`, `@Profile`, or bean conditions | Not an auto-configuration candidate |
| Want one auto-configuration to run before/after another | `@AutoConfiguration(before/after)` | This is **ordering**, not excluding configuration |
| Application needs JDBC but reports missing URL/driver | Provide proper datasource and driver configuration | Exclude may hide the root cause making an essential feature disappear |
| Want to use a different library instead of an existing one | Read auto-config conditions and choose starters/dependencies | May need to change dependencies or replacement beans rather than just excluding |

### 9.1. When is exclude reasonable?

For example, a message-processing service pulls in JDBC libraries via a transitive dependency but **does not use a database**. If datasource auto-configuration triggers unwanted initialization, excluding `DataSourceAutoConfiguration` can accurately reflect the architecture. Even so, check why the JDBC library is on the classpath and whether removing that dependency is preferable.

### 9.2. When is exclude a sign of fixing in the wrong direction?

For example, an application actually needs to access a database and reports:

~~~text
Failed to configure a DataSource
~~~

Using `exclude = DataSourceAutoConfiguration.class` might make that message disappear, but repositories, `JdbcTemplate`, or business beans needing a datasource will fail to function properly. The right fix is to verify the URL, driver, credentials, profile, and dependencies—not removing required foundational configuration just to get past startup.

### 9.3. Do not arbitrarily exclude internal configurations

Spring Boot recommends relying only on **auto-configuration class names** as the public interface permitted for exclusion, avoiding dependencies on nested classes, methods, or internal implementation details of auto-configurations. When upgrading Boot versions, verify the FQCNs and behavior of declared exclusions.

## 10. Debugging whether an auto-configuration was excluded

### 10.1. Using --debug to read the Condition Evaluation Report

Run the application with:

~~~bash
java -jar target/exclude-demo-1.0.0.jar --debug
~~~

Spring Boot's report shows which auto-configurations matched/did not match and the exclusions section in that environment. How to read it:

1. Search for the **fully qualified class name** to exclude, e.g., `org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration`.
2. Check whether it appears in the **Exclusions** list or equivalent output.
3. If the expected exclusion is missing, verify that the annotation is on the active application configuration, the class name matches the version, and check property sources.
4. If the bean still appears, trace **which configuration** registered it. Exclude does not remove application-declared beans.
5. If the application fails to start, read **Caused by** in the stack trace; the exclusion may have worked, while another bean still depends on what was removed.

In applications with Spring Boot Actuator, the `/actuator/conditions` endpoint can provide similar information when enabled and exposed appropriately. Diagnostic endpoint access must be controlled in deployment environments.

### 10.2. Factors that commonly cause different results

- **Version:** specifically Spring Boot 3.x or 4.x? Auto-config class imports may change.
- **Classpath:** are the JDBC starter, driver, user-written components, and transitive dependencies actually in the deployed artifact?
- **Annotation:** using `@SpringBootApplication(exclude=...)` or `@EnableAutoConfiguration(exclude=...)`? Is it placed on the configuration actually used by Boot to start?
- **Class name:** is the FQCN in `excludeName` / `spring.autoconfigure.exclude` exact?
- **Property source:** do profile configs, environment variables, or launch commands introduce exclusions outside annotations?
- **Bean origin:** did the bean come from auto-config, manual `@Bean`, component scan, or `@Import`?
- **Dependency errors:** does the application expect a bean that auto-config dropped?

Investigate from the **actual running application**; having an annotation in source code does not prove the container is booting with that specific application class.

## 11. Automated testing to prevent regressions

You can write a test to verify that when the application starts under its declared configuration, it does not auto-create a datasource. For the project in Section 5, file:

**src/test/java/demo/exclude/ExcludeDemoApplicationTest.java**

~~~java
package demo.exclude;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = ExcludeDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class ExcludeDemoApplicationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void datasourceAutoConfigurationIsExcluded() {
        assertThat(context.getBeanNamesForType(DataSource.class))
                .isEmpty();
    }
}
~~~

This test corresponds to the **version with exclude** in `ExcludeDemoApplication.java`. With `spring-boot-starter-test` declared in `pom.xml`, run:

~~~bash
mvn test
~~~

Expected **1 test PASS**: no `DataSource`. If you remove exclude as a control check, the test will fail in the lab because the default datasource returns, showing that the assertion actually detects the difference. When an application has a manual datasource bean, adjust the test criterion to check that **the configuration was excluded or the specific bean created by auto-config does not exist**; do not assert "no datasource" if the application's contract is to provide its own datasource.

You can expand tests for:
- One profile without exclude, another profile with exclude via `spring.autoconfigure.exclude`.
- A user-supplied bean still retained when the corresponding auto-configuration is excluded.
- A feature depending on the datasource not being mistakenly enabled when the datasource is absent.
- Boot version changes not breaking or invalidating names in `excludeName`.

## 12. Common mistakes

### Mistake 1 — Confusing auto-configuration with any @Configuration

A self-written `@Configuration` can be imported or component-scanned; it is **not automatically** an auto-configuration selected by Spring Boot. Exclude should only point to **auto-configuration classes recognized by Boot's mechanism**. If you want to drop a custom-defined configuration, change registration/scan configuration or its conditions.

### Mistake 2 — Confusing exclude with removing a dependency

`@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)` **does not remove** `spring-boot-starter-jdbc` or the driver from the JAR. If you do not want a library included, fix the dependency graph and build tool packaging.

### Mistake 3 — Expecting all related beans to disappear

Another configuration or application source can still create the same bean type. Excluding an auto-config **does not forbid** that bean from existing. Only checking actual beans and registration sources tells the truth.

### Mistake 4 — Adding @EnableAutoConfiguration alongside @SpringBootApplication

`@SpringBootApplication` already includes `@EnableAutoConfiguration`. There is no need to add a duplicate annotation just to specify `exclude`. Place exclusions in a clear, active location.

### Mistake 5 — Wrong package when using excludeName

Boot 3.3 example:

~~~text
org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

The short name `DataSourceAutoConfiguration` is not an FQCN. When upgrading Boot, packages can change, so check the API docs for the exact version.

### Mistake 6 — Using exclude to silence missing required configuration errors

An application needing a database whose datasource auto-config fails due to a missing driver/URL is an issue that must be fixed at the root cause. Excluding the auto-config will leave other beans missing dependencies or drop functionality.

### Mistake 7 — Confusing @ComponentScan(excludeFilters) with auto-config exclude

`excludeFilters` affects components discovered by **component scanning**; `@SpringBootApplication`'s `exclude` passes to the **auto-configuration import selection** mechanism. These two mechanisms target different things.

### Mistake 8 — Using exclusion to replace an activation condition

If a starter supports a standard property to turn off a small feature, consider that property before excluding the entire auto-configuration. Excluding the whole configuration may affect other foundational beans.

### Mistake 9 — Copying configuration from a different Spring Boot version

Class names, packages, and the set of auto-configurations can change across major versions. For example, Boot 3.3 code uses `org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration`; check Boot 4's specific API if the application runs that version.

### Mistake 10 — Failing to test dependent beans

After dropping an auto-configuration, other beans may be filtered out by conditions or fail dependency injection. Test both the excluded target and features relying on it.

## 13. Reasoning exercises

**Exercise 1.** The main class uses:

~~~java
@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
~~~

But another source has:

~~~java
@Bean
DataSource dataSource() { /* return a valid DataSource */ }
~~~

Is it guaranteed that there is no `DataSource` bean? **No.** Exclude only prevents auto-config from creating the bean; a user-declared `@Bean` can still register.

**Exercise 2.** The application uses `@SpringBootApplication`. Do you need to add `@EnableAutoConfiguration(exclude=...)` to drop an auto-config? **No.** Use `exclude` directly on `@SpringBootApplication`.

**Exercise 3.** An optional auto-config class is not on the compile classpath, yet you want to declare an exclusion by name. Which attribute do you use? **`excludeName`**, passing the FQCN as a string.

**Exercise 4.** To drop a `@Service` created by component scan, should you write `@SpringBootApplication(exclude=MyService.class)`? **No.** That is not an auto-configuration candidate; change scanning or bean registration conditions.

**Exercise 5.** Does excluding `DataSourceAutoConfiguration` make H2 disappear from Maven dependencies? **No.** The classpath only changes when modifying dependency/build configuration.

**Exercise 6.** On the same Boot version, do `@SpringBootApplication(exclude=X.class)` and `@Configuration + @EnableAutoConfiguration(exclude=X.class)` have the same effect of removing X from auto-configuration? **Yes.** However, `@SpringBootApplication` also includes component scanning and `@SpringBootConfiguration`; the two approaches are **not wholly equivalent** in context structure.

**Exercise 7.** Should exclude be used if missing datasource configuration stops an app that genuinely needs a DB from starting? **Not as the default fix.** You need to fix the URL/driver/profile/credentials or dependencies required for that mandatory feature.

## 14. Safe application checklist

1. Identify the **exact auto-configuration class** creating the unwanted bean/behavior; use `--debug` and the condition report if needed.
2. Confirm this is a **Boot-recognized auto-configuration**, not a regular `@Configuration` / `@Service`.
3. Clarify **why exclusion is needed** and which beans/features depend on it; avoid masking required configuration errors.
4. Choose the declaration: standard application class → `@SpringBootApplication(exclude=...)`; custom configuration → `@EnableAutoConfiguration(exclude=...)`.
5. If the class cannot be referenced at compile time, use `excludeName` and the **version-accurate FQCN**.
6. If management by environment rather than code is needed, consider `spring.autoconfigure.exclude`.
7. Package, re-run with the **exact deployment profile/classpath/artifact**, and inspect the actual beans.
8. Check the condition report, stack traces, and downstream beans to verify that excluding **did not break necessary functionality**.
9. Write tests confirming key behaviors: the excluded configuration does not unintentionally create beans, and user-defined beans are preserved as designed.

**Remember:** `exclude` on `@SpringBootApplication` and `@EnableAutoConfiguration` target **the same auto-configuration set**. The main difference is how configuration classes are organized; `excludeName` substitutes a fully qualified class name string for a class literal; neither replaces dependency management or application-defined beans.

## 15. Official references to verify by version

- [Spring Boot 3.3.13 Javadoc — @SpringBootApplication](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/SpringBootApplication.html).
- [Spring Boot 3.3.13 Javadoc — @EnableAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/EnableAutoConfiguration.html).
- [Spring Boot 3.3.13 Javadoc — DataSourceAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceAutoConfiguration.html).
- [Spring Boot Reference — Auto-configuration / Disabling Specific Auto-configuration Classes](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html).
- [Spring Boot Reference — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html).