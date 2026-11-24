# Distinguishing Spring Framework from Spring Boot

## 1. Essence: Spring Boot Is Built on Spring Framework

**Spring Framework** is the framework providing the foundational platform for Java application development: the IoC container, **Dependency Injection (DI)**, bean management, resources, events, AOP, transactions, data access, web programming, and many specialized modules. **Spring Boot** is a project built **on top of Spring Framework** that makes creating, configuring, packaging, and operating Spring applications easier through *auto-configuration*, *starters*, curated compatible dependency sets, and startup tooling.

Key takeaway: **Framework provides the core capabilities; Boot helps assemble and launch applications using those capabilities by convention.** Spring Boot **does not replace** the IoC container with a separate kind of container; beans still go through Spring concepts such as `ApplicationContext`, `BeanDefinition`, `@Bean`, `@Component`, and constructor injection.

Do not confuse these three points:
- A project with Spring Framework **does not have to** use Spring Boot: a console application can instantiate `AnnotationConfigApplicationContext` itself and manage the context lifecycle.
- A project using Spring Boot **still uses Spring Framework** underneath; APIs like `@Configuration`, `@Bean`, `@Component`, `@Autowired`, and `ApplicationContext` continue to work according to Framework rules.
- **Spring Boot does not mean a web application.** With the base starter and no Servlet/WebFlux libraries, Boot can run a console program or batch job without opening an HTTP port at all.

### Direct Comparison

| Question | Spring Framework (used directly) | Spring Boot |
| --- | --- | --- |
| What is it? | Multi-module framework: container, DI, web, transactions, etc. | Project/tooling **built on Framework** for convenient bootstrap and configuration |
| Who manages beans? | Spring IoC container (`ApplicationContext`/`BeanFactory`) | **The exact same Spring IoC container** |
| Typical entry point | Create `ApplicationContext` from Java/XML/programmatic config | `SpringApplication.run(...)` typically paired with `@SpringBootApplication` |
| Configuration declaration | `@Configuration`, `@Bean`, `@ComponentScan`, XML, etc. | Reuses those mechanisms; adds auto-configuration, starters, and property conventions |
| Dependency versions | Project selects/aligns manually or uses an appropriate BOM | Boot provides a BOM/parent managing a coordinated set of versions |
| HTTP server | Available when adding web modules + appropriate server bootstrap | **Appears only when** a web stack and matching conditions/config are present |
| Packaging | JAR/WAR depending on build configuration | Includes plugins to package executable JARs/WARs and run conveniently |
| Usable without web? | Yes | Yes |
| When preferred? | Learning IoC/DI clearly, minimal infrastructure control, or standalone libraries | Most applications needing convention-based startup/dependencies/config, web, or batch |

The table describes **defaults and common usage**, not two completely separate sets of APIs. Spring Framework can also use a BOM or modern build tools; Spring Boot also allows customizing every component when needed.

## 2. Where Does the Core Container Sit in Both Models?

In both startup approaches, **the Core Container is one and the same**:

~~~text
              APPLICATION BUSINESS LOGIC
     Service ----> Repository ----> Data source
                        ^
                        | dependency injection
                        |
           Spring ApplicationContext
            / BeanFactory / Bean graph
                 (Core Container)
                        ^
            +-----------+-----------+
            |                       |
   Using Framework directly       Using Spring Boot
   Create/configure context       SpringApplication.run(...)
   via code/XML                   + auto-configuration
            |                       |
            +--------- JVM ---------+
~~~

**Framework directly:** you typically instantiate `AnnotationConfigApplicationContext` yourself, specify `@Configuration` or `@ComponentScan`, register the relevant configuration, and close the context when done.

**Boot:** `SpringApplication.run` creates/prepares a context suited to the application type, registers your configuration sources, evaluates auto-configuration conditions, and runs the context startup process. Your beans are still created/injected through Framework. Business code like `GreetingService` does not need to import Spring Boot classes.

Specifically:

- **`spring-core`, `spring-beans`, `spring-context`, `spring-expression`** are foundational Framework modules. The `ApplicationContext` API belongs to Spring Framework, **not** exclusively to Boot.
- **`spring-boot`, `spring-boot-autoconfigure`, and `spring-boot-starter-...` artifacts** add bootstrap, conditional configuration, conventions, and convenient dependency bundles.
- In a Boot application with Spring MVC, Boot can configure the web server/DispatcherServlet/controllers when conditions hold. However, DispatcherServlet is a **Spring MVC** component; Boot helps wire it up when the stack and configuration allow.

**Do not believe the claim "Framework must configure everything with XML; only Boot uses annotations."** Java configuration with `@Configuration`/`@Bean` is already part of Framework; Boot inherits rather than reinvents it.

## 3. `@SpringBootApplication`: What Conveniences Are Enabled?

A Boot startup class is commonly written as:

~~~java
// Illustrative snippet, requires the appropriate Spring Boot dependency.
@SpringBootApplication
public class App {
    public static void main(String[] args) {
        SpringApplication.run(App.class, args);
    }
}
~~~

`@SpringBootApplication` combines three groups of meaning:

1. **`@SpringBootConfiguration`**: marks the class as a Spring configuration source; this annotation is a Boot-specific specialization of `@Configuration`.
2. **`@EnableAutoConfiguration`**: allows Boot to consider automatic configuration based on environment, classpath, properties, declared beans, and matching conditions.
3. **`@ComponentScan`**: scans components in the configuration class's package and its sub-packages by default rules. Therefore, place the main class in a **root package** covering your application code.

**`@SpringBootApplication` is not** merely `@Component`; it also activates Boot's auto-configuration and configuration-source mechanisms. Conversely, plain Framework still has `@ComponentScan` when declared explicitly; you do not need Boot to scan beans.

`SpringApplication.run(...)` returns a `ConfigurableApplicationContext` (an actual Spring context) that the application can use/close as needed. In web apps, context lifetime is usually tied to the server; in batch/console apps, design clear exit paths and resource lifecycles.

## 4. How Does Auto-Configuration Work and How Does It *Not* Work?

Auto-configuration is a mechanism that **conditionally contributes default beans/configurations**, not a system that guesses all your business logic. Configurations may depend on:

- **Classpath**: is a specific module, driver, or web stack present?
- **Existing beans**: a default configuration may skip creating a bean when the application already provides one with the matching role/type and condition.
- **Configuration properties**: for example, whether a feature is enabled/disabled or has an appropriate connection address.
- **Environment/application type**: console, Servlet web, or reactive web, profiles, etc.
- **Conditions Boot defines per configuration**: there is no universal rule that "having a JAR creates every bean."

Conditional annotations such as `@ConditionalOnClass`, `@ConditionalOnMissingBean`, and `@ConditionalOnProperty` commonly appear in auto-configurations. This is **not** a promise that every Boot feature uses all three of those conditions.

### A Simple Example

If you include a **web starter** and do not disable the web stack, Boot can auto-configure the appropriate HTTP components. If you only use `spring-boot-starter` without a Servlet/reactive stack, Boot runs as a non-web program without starting Tomcat.

If the application defines a specific bean, some auto-configurations **back off** (deferring to your bean) per their conditions; others remain active. Check the **conditions evaluation report** or that configuration's documentation rather than guessing from `@Bean` names.

Pass `--debug` when starting Boot to see additional condition evaluation details if logging configuration permits. The report tells you **why** an auto-configuration was or was not applied; it does not directly tell you whether your business service is right or wrong.

## 5. Starters, BOMs, Plugins, and Spring Initializr: What Does Each Do?

| Boot component | Practical effect | What it is not |
| --- | --- | --- |
| **Starter** (`spring-boot-starter`, web/data starters, etc.) | Bundles commonly used dependencies for a capability | A second IoC framework |
| **BOM/managed dependencies** | Manages compatible versions across many libraries | Automatically enabling every feature in those dependencies |
| **`spring-boot-starter-parent`** (Maven) | Parent build + dependency/plugin conventions | Mandatory if using Boot with Gradle or another Maven setup |
| **Boot Maven/Gradle plugin** | Runs/packages executable apps, build integration | A replacement for `javac` or the JVM |
| **Spring Initializr** (`start.spring.io`) | Project scaffolding tool with chosen metadata, build, and dependencies | Where the IoC container runs at runtime |
| **Externalized configuration** | Passes parameters via properties/YAML, environment, command line per Boot rules | Exemption from validating configuration values |

**Starters are not auto-configuration.** A starter is primarily a dependency bundle; auto-configuration is **conditional logic** running during Boot bootstrap. Because they are often used together, people easily mistake them for the same thing.

**Do not force a custom Spring Framework version** inside a Boot application without a controlled reason: Boot's BOM already aligns compatible versions. Arbitrarily overriding `spring-context` can break binary/API compatibility across modules.

When migrating projects between Spring Boot **3.x (based on Framework 6.x)** and **4.x (based on Framework 7.x)**, read the migration guides and review Jakarta/Servlet/testing/library changes. Both generations support **Java 17+**, which does not mean all older dependencies/features are immediately compatible.

## 6. Example 1 — Spring Framework Directly, Without Boot

This example creates an `ApplicationContext` **manually**, declares two beans, and prints the result. No Spring Boot or web server is needed.

### 6.1. Project Structure

~~~text
framework-console/
├── pom.xml
└── src/main/java/demo/FrameworkConsoleApp.java
~~~

### 6.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>framework-console</artifactId>
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
                    <mainClass>demo.FrameworkConsoleApp</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The example pins **Spring Framework 7.0.9** and release 17 for easy comparison. In real projects, use an appropriate maintained version and review migration docs when updating.

### 6.3. `src/main/java/demo/FrameworkConsoleApp.java`

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class FrameworkConsoleApp {
    private FrameworkConsoleApp() {
    }

    static final class PrefixSource {
        private final String prefix;

        PrefixSource(String prefix) {
            this.prefix = prefix;
        }

        String value() {
            return prefix;
        }
    }

    static final class GreetingService {
        private final PrefixSource source;

        GreetingService(PrefixSource source) {
            this.source = source;
        }

        String greet(String name) {
            return source.value() + ", " + name + "!";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {
        @Bean
        PrefixSource prefixSource() {
            return new PrefixSource("Xin chao");
        }

        @Bean
        GreetingService greetingService(PrefixSource source) {
            return new GreetingService(source);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            GreetingService service = context.getBean(GreetingService.class);
            System.out.println("framework.message=" + service.greet("Lan"));
            System.out.println("framework.singleton="
                    + (service == context.getBean(GreetingService.class)));
        }
    }
}
~~~

### 6.4. Build, Run, and Output

From the `framework-console` directory containing `pom.xml`, requiring JDK 17+ and Maven 3.9+:

~~~bash
java -version
mvn -version
mvn -q compile exec:java
~~~

**Two stdout lines printed by the application code** (excluding output from the two environment check commands and build/logging backend diagnostics):

~~~text
framework.message=Xin chao, Lan!
framework.singleton=true
~~~

`AnnotationConfigApplicationContext(Config.class)` creates the context and reads `Config`. The factory method `greetingService(PrefixSource source)` receives the `PrefixSource` bean resolved by the container, then creates `GreetingService`. Default scope is singleton, so two `getBean` calls for the same definition return the same reference. There is no `SpringApplication`, `@SpringBootApplication`, Boot starter, or auto-configuration in this program.

If you invoke bare `javac FrameworkConsoleApp.java` without placing Spring JARs on the classpath, the compiler will report missing packages. Maven manages the **transitive classpath** and invokes the compiler in the command above.

## 7. Example 2 — Spring Boot Reusing the Core Container, Still a Console App

The second example performs **the same functionality** while letting Spring Boot bootstrap the context. Without adding a web starter, the application is a console app and **does not start an HTTP server**.

### 7.1. Project Structure

~~~text
boot-console/
├── pom.xml
└── src/main/
    ├── java/demo/BootConsoleApp.java
    └── resources/application.properties
~~~

### 7.2. `pom.xml` and Boot-Managed Dependencies

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.1</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>boot-console</artifactId>
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

The **Boot 4.1.1** parent provides dependency management, so you do not need to specify separate versions for `spring-boot-starter` or `spring-context`. Boot 4.x corresponds to the Spring Framework 7.x generation; this example keeps JDK 17 as the compilation level. Do not mix `spring-boot-starter-parent 4.1.1` with a separately pinned `spring-context` 6.x.

### 7.3. `src/main/java/demo/BootConsoleApp.java`

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication(proxyBeanMethods = false)
public class BootConsoleApp {

    static final class PrefixSource {
        private final String prefix;

        PrefixSource(String prefix) {
            this.prefix = prefix;
        }

        String value() {
            return prefix;
        }
    }

    static final class GreetingService {
        private final PrefixSource source;

        GreetingService(PrefixSource source) {
            this.source = source;
        }

        String greet(String name) {
            return source.value() + ", " + name + "!";
        }
    }

    @Bean
    PrefixSource prefixSource() {
        return new PrefixSource("Xin chao");
    }

    @Bean
    GreetingService greetingService(PrefixSource source) {
        return new GreetingService(source);
    }

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(BootConsoleApp.class, args)) {
            GreetingService service = context.getBean(GreetingService.class);
            System.out.println("boot.message=" + service.greet("Lan"));
            System.out.println("boot.singleton="
                    + (service == context.getBean(GreetingService.class)));
        }
    }
}
~~~

Beans are still defined with `@Bean` and receive dependencies via parameters just like in direct Framework usage. The important difference is **how bootstrap/configuration occurs**: `SpringApplication.run` creates a Boot-configured context, applies eligible auto-configurations, reads external configuration, and manages startup steps. `@SpringBootApplication(proxyBeanMethods = false)` does not require factory methods to call one another; Spring injects via parameters when creating beans.

### 7.4. `src/main/resources/application.properties` and Running

~~~properties
spring.main.banner-mode=off
logging.level.root=OFF
~~~

These two settings **only suppress the banner/logs when running the example**; they do not decide whether the application has a web server. Because `spring-boot-starter-webmvc`, `spring-boot-starter-webflux`, or a server stack is not declared, the example is non-web.

Inside the `boot-console` directory:

~~~bash
java -version
mvn -version
mvn -q spring-boot:run
~~~

**Two lines produced by the `System.out.println` statements in the application code** (excluding Maven diagnostics, JVM info, or logs the environment might add):

~~~text
boot.message=Xin chao, Lan!
boot.singleton=true
~~~

You can also verify packaging:

~~~bash
mvn -q package
java -jar target/boot-console-1.0.0.jar
~~~

Boot's plugin creates an executable JAR with the required dependencies; this is a **build/packaging convenience**, not something that alters the meaning of `GreetingService` or Framework's singleton/DI rules.

**Startup note:** `BootConsoleApp` is in package `demo`; if you add `@Component` to `demo.service.MyService`, default component scanning includes that sub-package. If you place a bean in a package outside `demo`, register/scan it explicitly. In this example, both beans are declared with `@Bean` directly on the startup configuration so no separate `@Component` class is needed.

## 8. Comparing Output and Analyzing Why

| Observation | Plain Framework | Spring Boot |
| --- | --- | --- |
| Entry point | `main` uses `new AnnotationConfigApplicationContext(...)` | `main` uses `SpringApplication.run(...)` |
| Bean registration | `@Configuration` + `@Bean` | `@SpringBootApplication` + `@Bean` |
| Dependency injection | Factory method accepts `PrefixSource` | **Same rule:** factory method accepts `PrefixSource` |
| Retrieving beans | `context.getBean(GreetingService.class)` | **Same API:** `context.getBean(GreetingService.class)` |
| Two bean lookups | `framework.singleton=true` | `boot.singleton=true` |
| Greeting | `framework.message=Xin chao, Lan!` | `boot.message=Xin chao, Lan!` |
| Auto-configuration | No Boot auto-config mechanism in example | Boot mechanism active, applying conditions that actually match |
| HTTP server | No | No |
| Build/run | Exec Maven Plugin | Boot Maven Plugin, executable JAR |

In **both examples**, the plain Java service imports no Spring APIs. DI happens because of the factory methods; **the difference lies in who initializes the context and what infrastructure conveniences are added at startup**.

These two programs are not meant to prove Boot is "stronger" for this simple problem: in a small console app, Boot adds extra bootstrap/dependencies/plugins and may be unnecessary. In applications involving web, databases, environment-based configuration, and multiple integrations, Boot typically reduces manual configuration and coordinates consistent versions.

## 9. Misconceptions to Avoid

1. **"Spring Framework and Spring Boot are two different DI frameworks."** False. Boot reuses Framework's IoC container.
2. **"Using Framework requires XML."** False. `@Configuration`, `@Bean`, component scanning, and many configuration styles are already in Framework.
3. **"With Boot you don't need to understand Spring."** False. Scopes, bean lifecycles, wiring, proxies, and transactions still require understanding Framework mechanics to debug.
4. **"Auto-configuration writes business services automatically."** False. It configures **infrastructure conditionally**, not business rules.
5. **"Using Boot automatically gives you a REST API/Tomcat."** False. You need a web stack and matching startup conditions; a Boot console app does not necessarily have a server.
6. **"Starters are the same thing as auto-configuration."** False. Starters bundle dependencies; auto-configuration is conditional logic enabled during Boot bootstrap.
7. **"Boot replaces Maven, javac, or the JVM."** False. Boot assists with build tools and packaging, while the program is still compiled and run on standard Java tools and runtime.
8. **"Adding `@SpringBootApplication` scans every class in the project."** False. By default it scans from the main class's package down into sub-packages; this can be customized.
9. **"Spring Boot cannot be configured manually."** False. You can still define `@Bean` methods, properties, exclude auto-configurations, or use Framework configuration when needed.
10. **"Framework is the old version and Boot is the new replacement."** False. They are **two related projects** with their own release lines; Boot 4.x is typically built on Framework 7.x, not replacing a discontinued Framework.

## 10. When to Choose Which?

Choose **Framework directly** when the goal is:
- Studying `ApplicationContext`, bean registration, DI/lifecycle, object creation conditions in depth, or building a minimal container setup.
- Writing a library/integration without imposing all of Boot's conventions on consumers.
- Building a small console tool with a simple dependency graph, or needing explicit control over every module and bootstrap step.

Choose **Boot** when the goal is:
- Building a real-world application needing web/data/messaging/observability without manually coordinating many dependencies/configurations.
- Needing conventions for externalized configuration, profiles, test/build/run/package, and runtime operations.
- Collaborating in a team where fast project initialization and reproducible dependency versions matter.
- Using a starter + properties to leverage Framework capabilities and integrated libraries quickly.

**This is not an absolute mutually exclusive technical choice.** A Boot app can use most Framework APIs; a non-Boot Framework app can still scale cleanly and use advanced features when configured well. Choose based on development cost, infrastructure, and needs, not slogans.

### Upgrades and Version Management

- The examples pin **Framework 7.0.9** and **Boot 4.1.1** to present concrete configurations clearly. They do not imply those are always the latest recommended versions at every point in time.
- Boot 4.x requires Java 17+ and the Framework 7.x foundation, along with Jakarta EE 11 changes. When upgrading from Boot 3.x, read the migration guide; do not copy configurations, web starters, or plugins between the two generations without checking.
- Follow supported patch releases and security advisories for production use, and verify the dependency tree and build tests after upgrading.

## 11. Self-Check Exercises

1. **Change the `PrefixSource` implementation** to return `"Hello"` in each example. Predict the two `message` lines; why does the output change without editing `GreetingService`?
2. **Add a second bean of type `PrefixSource`** with a different name. Predict the ambiguity error on the `greetingService(PrefixSource source)` factory method; explore using `@Primary`, `@Qualifier`, or an appropriate bean selection contract.
3. **Intentionally disable an auto-configuration in Boot** for an infrastructure component (once you have learned that feature). Check actual conditions before and after; do not claim `@EnableAutoConfiguration` always creates every bean.
4. **Turn the Boot console app into a web app** with the matching-generation web starter and a controller; identify what Spring MVC provides, what Boot assembles automatically, and when the HTTP server opens a port. Do not assume adding `@RestController` to a project without a web stack is enough to receive HTTP requests.
5. **Remove the Boot Maven parent** and switch to importing the BOM and declaring plugins explicitly. Point out what still must be declared for `spring-boot:run` and executable JAR packaging to work.
6. **Compare tests:** construct a `GreetingService` with `new` and a fake `PrefixSource` (no Spring), then test via a context. When are plain Java tests faster/more useful, and when is a container test needed?
7. **Analyze startup:** compare `new AnnotationConfigApplicationContext(...)` with `SpringApplication.run(...)` across configuration loading, bean registration, DI resolution, and lifecycle, noting similarities and differences.

### Mastery Checklist

- [ ] Accurately state **what Framework provides**, **what Boot adds**, and **how they relate**.
- [ ] Explain why both use Spring's `ApplicationContext` and bean graph.
- [ ] Identify the effects of all three parts inside `@SpringBootApplication`.
- [ ] Distinguish starters, dependency management, auto-configuration, plugins, and Initializr.
- [ ] Explain why the Boot example with only the base starter **does not open an HTTP server**.
- [ ] Run both Java 17 Maven projects yourself, predict the four application stdout lines, and distinguish them from logs.
- [ ] Know when Boot is helpful and when direct Framework is sufficient.

## 12. Official Documentation for Version-Accurate Learning

- [Spring Framework – Overview](https://docs.spring.io/spring-framework/reference/overview.html)
- [Spring Framework – The IoC Container](https://docs.spring.io/spring-framework/reference/core/beans.html)
- [Spring Framework – Container Overview](https://docs.spring.io/spring-framework/reference/core/beans/basics.html)
- [Spring Boot – Getting Started](https://docs.spring.io/spring-boot/reference/getting-started/index.html)
- [Spring Boot – Using @SpringBootApplication](https://docs.spring.io/spring-boot/reference/using/using-the-springbootapplication-annotation.html)
- [Spring Boot – Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html)
- [Spring Boot – Build Systems and Starters](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
- [Spring Initializr](https://start.spring.io/)

**Conclusion:** Spring Framework provides the **IoC/DI foundation and application modules**, while Spring Boot adds **startup conventions, auto-configuration, starters, and tooling** to use that foundation faster and more consistently. Learning Boot effectively requires understanding beans, dependency injection, scopes, lifecycles, and the boundaries of the underlying Core Container.