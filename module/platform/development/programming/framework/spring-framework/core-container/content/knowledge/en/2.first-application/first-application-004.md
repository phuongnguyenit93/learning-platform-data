# Initializing `AnnotationConfigApplicationContext` in Spring Framework

## 1. Purpose and Role of the Context

`AnnotationConfigApplicationContext` is an **implementation of `ApplicationContext`** in `spring-context` used to bootstrap the Spring IoC container from annotation/Java configuration without XML files. It accepts `@Configuration` classes, component classes (`@Component`, `@Service`...), or a list of packages for component scanning, then registers **bean definitions**, creates/wires matching beans, and provides the `getBean(...)` API.

In this lesson, we learn precisely **when the context is initialized, when `refresh()` is needed, how to retrieve beans, and how to close the context**. This is a **pure Spring Framework** program, without `SpringApplication.run(...)`, Spring Boot, or a web server.

Desired outcomes:
- Initialize a context with `new AnnotationConfigApplicationContext(AppConfig.class)`.
- Understand the equivalent approach using `new AnnotationConfigApplicationContext()`, followed by `register(AppConfig.class)` and `refresh()`.
- Know when to use `scan("demo.components")`, and why merely placing `@Component` does not make a bean appear automatically.
- Query `getBean(Class<T>)`, `containsBean(...)`, check singleton behavior, and close the container with `try-with-resources`.
- Diagnose forgetting `refresh()`, scanning the wrong package, duplicate beans by type, missing dependencies, and calling `refresh()` at the wrong point in the lifecycle.

Prerequisites: **JDK 17+**, **Maven 3.9+**, and access to Maven Central/mirror for initial dependency downloads. Examples use Spring Framework **7.0.9**; Spring 7.0 maintains a Java 17 baseline. This version is pinned for lesson reproducibility, not a mandate to stay on it permanently in production.

## 2. Where Does `AnnotationConfigApplicationContext` Fit?

Related classes and interfaces:

| Type | Role |
| --- | --- |
| `BeanFactory` | Core API for accessing beans managed by the container |
| `ApplicationContext` | Extends BeanFactory capabilities with events, resources, message sources... |
| `ConfigurableApplicationContext` | Contract for configuring/managing context lifecycle (including `refresh()`, `close()`) |
| `AnnotationConfigApplicationContext` | Concrete implementation reading annotation configuration, supporting `register`, `scan`, `registerBean` |

Packages to import when writing code:

~~~java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
~~~

These three lines are an **illustrative import snippet**, used in the complete program in Section 5. They are not a standalone Java program.

`@Bean` declares a **factory method** returning a Spring-managed object. `@Configuration` marks a class as a configuration source. `ApplicationContext` is the container that uses that metadata to create, wire, and manage beans; it does **not** automatically instantiate every Java object on the classpath.

Distinctions:
- `new AnnotationConfigApplicationContext(...)` creates the **container/context**, not a business service.
- `context.getBean(GreetingService.class)` retrieves the registered **service bean** created according to its scope.
- `new GreetingService(...)` manually constructs a Java object outside Spring; it does not participate in container lifecycle/DI.
- `@Component` on a class becomes a bean only when the class is **registered/scanned** by an appropriate context.

## 3. Three Initialization Styles: Which Ones Auto-`refresh()`?

| Usage | Context Auto-`refresh()`? | When Appropriate |
| --- | --- | --- |
| `new AnnotationConfigApplicationContext(AppConfig.class)` | **Yes** | One or more config classes are ready and you want quick startup |
| `new AnnotationConfigApplicationContext("demo.components")` | **Yes** | Package to scan is known and you want immediate scanning on creation |
| `new AnnotationConfigApplicationContext()` then `register(...)` | **No**: you must call `refresh()` | Need to combine multiple configuration sources or prepare context before bootstrap |
| `new AnnotationConfigApplicationContext()` then `scan(...)` | **No**: you must call `refresh()` | Want explicit control over package scanning before bootstrap |

**Syntax summary** example, using `AppConfig` declared in Section 5:

~~~java
// Quick approach: constructor taking class(es) refreshes automatically before returning.
try (var ctx = new AnnotationConfigApplicationContext(AppConfig.class)) {
    var service = ctx.getBean(GreetingService.class);
}

// Step-by-step approach: manual refresh is required.
try (var ctx = new AnnotationConfigApplicationContext()) {
    ctx.register(AppConfig.class);
    ctx.refresh();
    var service = ctx.getBean(GreetingService.class);
}
~~~

The block above illustrates **code placed inside a method with matching imports and types**. In the complete demo, it is implemented as a compilable Java class.

The constructor `new AnnotationConfigApplicationContext(AppConfig.class, MoreConfig.class)` can also take multiple classes. Similarly, `register(...)` can be called multiple times **before** `refresh()`. Once bootstrapped, work with the active context instead of treating this context type as infinitely re-refreshable.

**Important:** `AnnotationConfigApplicationContext` extends `GenericApplicationContext`, which has **single-refresh** semantics per context. Do not call `refresh()` a second time after a config-accepting constructor has auto-refreshed or after a manual refresh. To rebuild a container from new sources, normally create a new context.

## 4. Inside the `refresh()` Step

Simplified model:

~~~text
Create empty context / pass configuration in constructor
                     |
        Register config class or scan
                     |
      Determine bean-definition metadata
                     |
                refresh()
                     |
     Run metadata post-processing steps
                     |
       Resolve dependencies and scopes
                     |
       Instantiate non-lazy singleton beans
                     |
          Inject dependencies / init hooks
                     |
             Context ready
                     |
        getBean(...) / invoke business logic
                     |
       close() / destruction callbacks
~~~

`refresh()` is not just “flipping a ready flag”: it is the **bootstrap step** that configures the bean factory, processes configuration definitions, registers post-processors, instantiates non-lazy singletons, publishes lifecycle events, and completes steps needed before the context can be used. Scopes and lazy configuration can mean some instances are **not created immediately** at refresh; definitions can exist before instances.

Calling `register(AppConfig.class)` only designates the **configuration source**; `@Bean` methods are not necessarily processed yet and beans are not ready for retrieval until refresh runs.

With the constructor taking `AppConfig.class`, `register` and `refresh` happen inside the constructor **before it returns**. Thus, right after `new AnnotationConfigApplicationContext(AppConfig.class)`, calling `getBean` is valid if bootstrap succeeded.

**Do not equate `refresh()` timing with every object's creation timing.** `@Lazy` and prototype beans follow their own rules; `getBean` can create a new prototype instance, whereas singletons are shared by default.

## 5. Standalone Java 17 Maven Project: Constructor vs. `register + refresh`

### 5.1. Structure

~~~text
context-bootstrap-demo/
├── pom.xml
└── src/main/java/
    └── demo/
        ├── ContextBootstrapDemo.java
        ├── ScanBootstrapDemo.java
        └── components/
            └── ScanGreeting.java
~~~

This is **one Maven project** with two main classes. You can run them one after another without modifying the POM or adding Spring Boot. `ScanGreeting` supports the scan approach in Section 6.

### 5.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>context-bootstrap-demo</artifactId>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` can pull in foundational Spring artifacts such as `spring-core`, `spring-beans`, and `spring-expression` per Maven metadata. You do not have to add `spring-boot-starter`. Maven Compiler Plugin uses `--release 17` from the declared property. Exec Maven Plugin runs the main class specified via `-Dexec.mainClass`.

### 5.3. `src/main/java/demo/ContextBootstrapDemo.java`

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class ContextBootstrapDemo {

    private ContextBootstrapDemo() {
    }

    interface Greeter {
        String greet(String name);
    }

    static final class DefaultGreeter implements Greeter {
        @Override
        public String greet(String name) {
            return "Hello, " + name + "!";
        }
    }

    static final class GreetingService {
        private final Greeter greeter;

        GreetingService(Greeter greeter) {
            this.greeter = greeter;
        }

        String greet(String name) {
            return greeter.greet(name);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {
        @Bean
        Greeter greeter() {
            return new DefaultGreeter();
        }

        @Bean
        GreetingService greetingService(Greeter greeter) {
            return new GreetingService(greeter);
        }
    }

    private static void inspect(
            String label, AnnotationConfigApplicationContext ctx) {
        GreetingService service = ctx.getBean(GreetingService.class);

        System.out.println(label + ".message=" + service.greet("An"));
        System.out.println(label + ".singleton="
                + (service == ctx.getBean(GreetingService.class)));
        System.out.println(label + ".active=" + ctx.isActive());
    }

    public static void main(String[] args) {
        // Approach 1: constructor taking config class refreshes automatically.
        try (var direct =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            inspect("direct", direct);
        }

        // Approach 2: create context, register, then refresh once.
        try (var manual = new AnnotationConfigApplicationContext()) {
            manual.register(AppConfig.class);
            manual.refresh();
            inspect("manual", manual);
        }
    }
}
~~~

**Code Walkthrough:**

- `AppConfig` is registered as a configuration source. Two `@Bean` factory methods create `Greeter` and `GreetingService`.
- `greetingService(Greeter greeter)` receives its dependency from the container; it does not call `greeter()` directly, matching `proxyBeanMethods=false`.
- Inside `inspect`, `getBean(GreetingService.class)` retrieves the bean from the corresponding context. Because the default scope is singleton, **two lookups in the same context** return the same reference.
- `direct` and `manual` are **two independent contexts**, meaning they do not share singletons. Each context building its own bean graph is expected.
- `isActive()` shows the context is active while `inspect` runs; `close()` happens after the print statements because `try-with-resources` manages the resource automatically.

### 5.4. Build, Run, and Expected Stdout

From the directory containing `pom.xml`, check:

~~~bash
java -version
javac -version
mvn -version
~~~

Run the first main class; quoting `-Dexec.mainClass=...` works in both Bash and PowerShell:

~~~bash
mvn -q clean compile exec:java "-Dexec.mainClass=demo.ContextBootstrapDemo"
~~~

**Six stdout lines from the program itself** (excluding `java -version`/`mvn -version` output, build logs, or logging backend output):

~~~text
direct.message=Hello, An!
direct.singleton=true
direct.active=true
manual.message=Hello, An!
manual.singleton=true
manual.active=true
~~~

No HTTP port is opened. The program exits after both contexts are closed in turn. Spring configuration logs may appear depending on the environment, but they are not part of the six lines produced by `System.out.println`.

If `javac` reports it cannot find `org.springframework.context.annotation`, you may have compiled manually without a classpath. Run from the right directory via Maven so transitive dependencies are resolved.

## 6. Same Project, Third Approach: Component Scan

With component scanning, you do not have to list every concrete class upfront, but you **must specify the right package** and classes to scan must carry appropriate metadata (for example `@Component`).

### 6.1. `src/main/java/demo/components/ScanGreeting.java`

~~~java
package demo.components;

import org.springframework.stereotype.Component;

@Component
public class ScanGreeting {
    public String message() {
        return "scanned bean ready";
    }
}
~~~

### 6.2. `src/main/java/demo/ScanBootstrapDemo.java`

~~~java
package demo;

import demo.components.ScanGreeting;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public final class ScanBootstrapDemo {
    private ScanBootstrapDemo() {
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext()) {
            context.scan("demo.components");
            context.refresh();

            ScanGreeting greeting = context.getBean(ScanGreeting.class);
            System.out.println("scan.message=" + greeting.message());
            System.out.println("scan.name="
                    + context.containsBean("scanGreeting"));
            System.out.println("scan.active=" + context.isActive());
        }
    }
}
~~~

`scan("demo.components")` searches for candidate components in the requested package and its subpackages; it does not scan the entire classpath automatically. `ScanGreeting` has `@Component`, so it is registered in the context. The default bean name from component scanning here is `scanGreeting` (following Spring's default naming strategy).

Run the second program using the same POM:

~~~bash
mvn -q compile exec:java "-Dexec.mainClass=demo.ScanBootstrapDemo"
~~~

**Three stdout lines from the second program:**

~~~text
scan.message=scanned bean ready
scan.name=true
scan.active=true
~~~

Using the package-accepting constructor also works: `new AnnotationConfigApplicationContext("demo.components")` will **scan and refresh automatically**. When coordinating multiple packages or combining `register` and `scan`, creating an empty context and calling `refresh()` once is often clearer.

**Limitation:** `@Component` takes effect only when the class is registered or found by the active context's scan. If you use `scan("demo.unrelated")` instead of the actual package, `getBean(ScanGreeting.class)` will not find the bean. This is not a Java syntax error; it is a bean-graph configuration error.

## 7. Lifecycle: Closing the Context and Handling Bootstrap Failures

`AnnotationConfigApplicationContext` implements `AutoCloseable` through the context contract, so `try-with-resources` ensures `close()` is called upon exiting the block, even if an exception occurs during use.

~~~java
// Illustrative snippet placed inside a method with AppConfig and proper imports.
try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
    // Use beans here.
} // close() is called automatically.
~~~

This is a **non-standalone** illustrative snippet; the complete program is in Section 5.

**Closing the context does not mean Java GC immediately destroys all objects.** Spring runs destruction callbacks for eligible managed beans (especially singletons); Java references held elsewhere still follow normal lifetime/GC rules. Prototypes have different destruction rules: the container generally does not manage full destruction after handing out an instance.

A context can **fail to start** if:
- A configuration class is invalid or a factory method throws an exception.
- A required bean for a constructor/`@Bean` factory method parameter is missing.
- Multiple bean candidates match a dependency type with no disambiguation rule.
- Constructor dependencies form an unresolvable cycle.
- Component scanning fails to find a component expected by the application.

When a failure happens inside a self-refreshing constructor (such as `new AnnotationConfigApplicationContext(AppConfig.class)`), the constructor can **throw an exception before assigning the context variable**. Do not rely on retrieving a context from an incomplete constructor to call `close()`; handle startup exceptions, inspect the root cause in logs/stack traces, and ensure external resources are cleaned up properly.

## 8. Right and Wrong Usage Patterns

| Scenario | Right/Wrong | Reason |
| --- | --- | --- |
| `new AnnotationConfigApplicationContext(AppConfig.class)` then `getBean` | Right | Constructor automatically registers + refreshes |
| `new AnnotationConfigApplicationContext()`, `register(...)`, `refresh()` | Right | Completes bootstrap manually before lookup |
| `new AnnotationConfigApplicationContext()`, `scan(...)`, `refresh()` | Right | Scans package then bootstraps |
| Create empty context, `register(...)`, then call `getBean` **immediately** | Wrong | Not refreshed yet |
| Constructor taking class then calling `refresh()` again | Wrong | This context type is not a multi-refresh context |
| `@Component` in a package neither scanned nor registered | Insufficient | Annotation alone does not create a bean |
| Calling `getBean(SomeType.class)` when no bean exists | Runtime error | Usually `NoSuchBeanDefinitionException` |
| Lookup by type when multiple equal candidates exist | May fail | Usually `NoUniqueBeanDefinitionException` |
| Creating multiple contexts and assuming singletons are shared JVM-wide | Wrong | Singletons normally apply per bean definition/context |
| Leaving resource-holding console context unclosed | Discouraged | May skip lifecycle callbacks and cleanup |

`refresh()` is the crucial boundary between **declaring configuration sources** and a **started container**. Some `BeanDefinition` entries may be registered early, but relying on `getBean` before refresh is improper usage of an inactive `ApplicationContext`.

In a web/Boot project, bootstrap and shutdown are typically tied to `SpringApplication`/the server. This lesson focuses strictly on initializing `AnnotationConfigApplicationContext` **manually**.

## 9. Troubleshooting Common Errors When Running the Samples

| Symptom | Likely Cause | How to Verify/Fix |
| --- | --- | --- |
| `package org.springframework.context... does not exist` | `spring-context` missing from compile classpath | Check POM, run Maven in the right directory, reload IDE |
| `NoSuchBeanDefinitionException` for `GreetingService` | Forgot to register `AppConfig` or configuration not processed | Check registered sources and ensure `refresh()` is called |
| `NoSuchBeanDefinitionException` for `ScanGreeting` | Wrong package scanned / missing `@Component` | Verify `demo.components`, package name, and annotation |
| `IllegalStateException` about not refreshed | Created empty context and called lookup immediately | Call `register`/`scan` first and `refresh` exactly once |
| Exception on second `refresh` | Already refreshed via constructor or earlier call | Do not call twice; create a new context to re-bootstrap |
| `NoUniqueBeanDefinitionException` | Multiple beans match one type | Use `@Primary`, `@Qualifier`, or lookup by bean name |
| `BeanCreationException` | Error creating bean or dependency | Inspect `Caused by`, constructors, and factory methods |
| Java runtime older than build target | JDK/target runtime mismatch | Check `java -version`, `mvn -version`, compiler release |
| Maven fails to download `spring-context` | Version/repository/proxy/mirror/offline issue | Check GAV coordinates, Maven Central, and network settings |
| Demo prints output and process exits | Console context closed | Expected behavior for the demo, not necessarily an error |

**Remember:** a `getBean` failure may be a **metadata/configuration** issue rather than a “missing JAR”; conversely, `ClassNotFoundException`/compile-time package errors usually belong to dependencies/classpath. Separate the layers before editing code.

### Inspection Utilities

- Use `context.containsBean("greetingService")` to check whether a bean name is known in the context.
- Use `context.getBeanDefinitionCount()` or `getBeanDefinitionNames()` when debugging registration, but **do not hardcode the total count for the whole context**: Spring may register internal beans as well.
- Use `context.getBean(GreetingService.class)` to verify a specific type; avoid overusing it inside every service, as that creates the service-locator anti-pattern.
- Use logger/cause chains when startup fails; do not depend on exact exception message strings, which may change across patches.

## 10. Independent Practice Exercises

Perform **one exercise at a time**, restoring the original source between exercises to compare against Section 5/6 stdout:

1. **Swap bootstrap style:** replace `new AnnotationConfigApplicationContext(AppConfig.class)` with the 3-line no-arg/`register`/`refresh` form; predict whether the three `direct.*` lines change if you keep the label.
2. **Remove `refresh()`** in the `manual` branch: observe the exception when retrieving the bean. Explain why `register` does not mean the context has started.
3. **Call `refresh()` twice** on the no-arg branch: test on a copy, observe the error, and explain why a new context must be created to restart this context type.
4. **Wrong scan package:** change to `demo.missing`; predict whether `ScanGreeting` becomes a bean.
5. **Rename the bean:** put `@Component("welcomeComponent")` on `ScanGreeting` and update `containsBean(...)`; compare lookup by name vs. by type.
6. **Add a second `Greeter` bean:** predict ambiguous dependency in `greetingService(Greeter)`; resolve with `@Primary` or `@Qualifier`.
7. **Extract config file:** move `AppConfig` to a public `demo.config.AppConfig` and pass `AppConfig.class` to the constructor; observe that the output stays identical.
8. **Add a lifecycle callback:** create a bean with `@Bean(destroyMethod = "close")` and a `close()` method that prints a message; verify it runs on exiting try-with-resources (separate it from the original demo's standard stdout).
9. **Compare singletons across contexts:** retrieve one bean from each context and print `==`; explain why the same bean class does not mean the same object across two contexts.
10. **Switch `@Lazy` or `@Scope("prototype")`:** predict creation timing and reference comparison results; understand how this differs from “has the context refreshed yet?”.

### Self-Assessment Checklist

- [ ] Distinguish the `AnnotationConfigApplicationContext` class from business beans.
- [ ] Know the **two constructors** that auto-`refresh` (taking config classes / taking package strings).
- [ ] Know that the **no-arg** constructor needs `register` or `scan` followed by `refresh()`.
- [ ] Know how `@Configuration`, `@Bean`, and `@Component` enter the container.
- [ ] Run both main classes in the same Maven project and predict the exact 6+3 stdout lines.
- [ ] Never call `refresh()` a second time on `AnnotationConfigApplicationContext`.
- [ ] Know how to close the context and distinguish Spring lifecycle from Java garbage collection.

## 11. Summary and Official Documentation

- **Quick approach:** `new AnnotationConfigApplicationContext(AppConfig.class)` — config is registered and context refreshes automatically.
- **Explicit approach:** `new AnnotationConfigApplicationContext()` → `register(AppConfig.class)` → `refresh()`.
- **Scanning approach:** `new AnnotationConfigApplicationContext()` → `scan("demo.components")` → `refresh()`.
- `getBean(...)` requires a successfully bootstrapped context; scope/lazy settings decide when instances are created.
- `try-with-resources` closes the context and triggers appropriate lifecycle callbacks.
- **No Spring Boot or HTTP server** is used in these examples; everything runs on Spring Framework's Core Container.

Reference documentation:

- [Spring Framework – Instantiating the Spring Container](https://docs.spring.io/spring-framework/reference/core/beans/java/instantiating-container.html)
- [Spring Framework – Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html)
- [Spring Framework – Using @Bean](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
- [Spring Framework – Annotation-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config.html)
- [Spring Framework – Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Spring Framework 7.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes)

**Conclusion:** Whenever you open an `AnnotationConfigApplicationContext` yourself, be certain **whether configuration sources have been registered or scanned**, **whether `refresh()` has been called**, and **who is responsible for closing it**. Mastering those three steps lets you build and debug your first IoC/DI application without confusing initialization with bean retrieval.