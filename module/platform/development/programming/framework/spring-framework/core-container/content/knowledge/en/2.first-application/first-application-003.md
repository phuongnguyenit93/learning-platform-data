# Declaring Minimal Configuration with @Configuration and @Bean in Spring Framework

## 1. Learning Outcomes

Your first Spring Framework application can require only **JDK 17+, the `spring-context` dependency, one `@Configuration` class, a few `@Bean` factory methods, and a `main` method**. You do not need Spring Boot, XML, an HTTP server, or a database to observe the container managing beans.

By the end of this lesson, you will be able to:

- Create a Maven project with `spring-context` and compile on Java 17.
- Explain how `@Configuration` registers a configuration source and `@Bean` describes a factory method supplying a bean object to the container.
- Declare two collaborating beans and inject dependencies via `@Bean` method parameters without letting the business class call the container.
- Instantiate `AnnotationConfigApplicationContext`, verify bean names, retrieve beans by type, and check wiring and default scope.
- Distinguish normal Java method calls from Spring invoking factory methods, especially with `proxyBeanMethods=false`.
- Close the context safely and verify exact Java 17 execution commands and outputs.
- Diagnose missing beans, multiple candidates, wrong bean names, unregistered configurations, missing classpath entries, and duplicate registrations.

The scope of this lesson is **minimal JavaConfig**. Mechanisms such as component scanning, property injection, custom scopes, and Spring Boot auto-configuration are mentioned only where helpful to prevent conceptual confusion.

## 2. Before Spring: Consumer Class and Dependency Provider Class

Suppose the program needs to greet users. We have a `GreetingTemplate` contract and a service that uses that contract:

~~~java
interface GreetingTemplate {
    String render(String name);
}

final class VietnameseTemplate implements GreetingTemplate {
    @Override
    public String render(String name) {
        return "Xin chao, " + name + "!";
    }
}

final class GreetingService {
    private final GreetingTemplate template;

    GreetingService(GreetingTemplate template) {
        this.template = java.util.Objects.requireNonNull(template);
    }

    String greet(String name) {
        return template.render(name.strip());
    }
}
~~~

This is an **illustrative code snippet**, not a standalone runnable file (it lacks a `main` class). If wired manually in plain Java:

~~~java
GreetingTemplate template = new VietnameseTemplate();
GreetingService service = new GreetingService(template);
System.out.println(service.greet(" Lan ")); // Xin chao, Lan!
~~~

That is already **constructor dependency injection**: the service receives a collaborator chosen from outside, instead of calling `new VietnameseTemplate()` inside the business class. Spring helps **assemble objects according to bean definitions**; it does not invent a new Java language and does not forbid `new`: inside a `@Bean` factory method, `new` is the natural way to supply an object.

A service class knows `GreetingTemplate`; it does not need to know `ApplicationContext` or Maven. If you switch to `EnglishTemplate` in configuration, the service code does not need to change as long as the contract is honored.

## 3. What Does a Minimal Configuration Consist Of?

A short Java configuration:

~~~java
@Configuration(proxyBeanMethods = false)
class AppConfig {
    @Bean
    GreetingTemplate greetingTemplate() {
        return new VietnameseTemplate();
    }

    @Bean
    GreetingService greetingService(GreetingTemplate template) {
        return new GreetingService(template);
    }
}
~~~

This is an **illustration** omitting imports and related class definitions. The complete example is in Section 5.

| Syntax | Meaning in This Lesson |
| --- | --- |
| `@Configuration` | Class containing configuration that Spring processes into bean definitions |
| `@Bean` | Factory method creating/returning a bean object managed by the container |
| `greetingTemplate()` | Default bean name is typically `greetingTemplate` |
| `greetingService(GreetingTemplate template)` | Factory method parameter indicates a dependency to resolve |
| `new GreetingService(template)` | Constructor invoked by the factory method to wire the dependency |
| `proxyBeanMethods=false` | Does not intercept direct Java calls between `@Bean` factory methods |

**Key point:** the `greetingService(...)` factory method does not call `greetingTemplate()` directly. Spring sees the parameter requires a `GreetingTemplate` and supplies the matching bean. Thus the service receives the exact container-managed object.

~~~mermaid
flowchart LR
    C["ApplicationContext"] --> R["Bean: greetingTemplate"]
    C --> S["Bean: greetingService"]
    S -->|"constructor dependency"| R
~~~

The edge direction `greetingService → greetingTemplate` means **the service depends on the template**, not that the service must hold a reference to the context. Beans can be instantiated in an order that satisfies required dependencies, not strictly by method order in the file.

### Bean Definition vs. Bean Instance

- **Bean definition**: metadata stored by the container about name, factory method, resolvable type/scope, creation recipe, and related settings.
- **Bean instance**: the actual object supplied by the factory method and managed by the container. It does not appear automatically just because the source has annotations; the configuration class must **be registered and processed**.
- **Dependency injection**: supplying collaborators into constructors, factory parameters, or supported injection points.
- **Default scope**: `singleton` per **bean definition within a single context**, not one instance across the entire JVM.

In a typical context, **non-lazy** singletons are instantiated during the refresh phase; lazy or prototype beans follow different instantiation timing rules. Do not conclude every bean is created immediately the moment the registry receives metadata.

## 4. Creating the Maven Project on Java 17

Use **Spring Framework 7.0.9**, matching the dependency setup lesson; this is a **pinned version for reproducibility**, not a claim about the latest release. JDK 17+ and Maven are required. Spring Boot is not needed.

Directory layout:

~~~text
minimal-spring-config/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── MinimalConfigDemo.java
~~~

The `demo` package file resides in `src/main/java/demo/`. Java requires the filename to match the public top-level class `MinimalConfigDemo`.

### 4.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>minimal-spring-config</artifactId>
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
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.MinimalConfigDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The `spring-context` module pulls in transitive dependencies from related Spring modules. Maven downloads them automatically; do not copy a single standalone JAR and assume the classpath is complete. Offline, Maven runs only if all required artifacts are already in the local cache.

### 4.2. Complete Java File

Create `src/main/java/demo/MinimalConfigDemo.java`:

~~~java
package demo;

import java.util.Objects;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class MinimalConfigDemo {
    private MinimalConfigDemo() {}

    public interface GreetingTemplate {
        String render(String name);
    }

    public static final class VietnameseTemplate
            implements GreetingTemplate {
        @Override
        public String render(String name) {
            return "Xin chao, " + name + "!";
        }
    }

    public static final class GreetingService {
        private final GreetingTemplate template;

        public GreetingService(GreetingTemplate template) {
            this.template = Objects.requireNonNull(
                    template, "template must not be null");
        }

        public String greet(String rawName) {
            if (rawName == null || rawName.isBlank()) {
                throw new IllegalArgumentException("name must not be blank");
            }
            return template.render(rawName.strip());
        }

        public GreetingTemplate template() {
            return template;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public GreetingTemplate greetingTemplate() {
            return new VietnameseTemplate();
        }

        @Bean
        public GreetingService greetingService(
                GreetingTemplate template) {
            return new GreetingService(template);
        }
    }

    public static void main(String[] args) {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class);

        try (context) {
            boolean definitions =
                    context.containsBeanDefinition("greetingTemplate")
                    && context.containsBeanDefinition("greetingService");

            GreetingTemplate template =
                    context.getBean(GreetingTemplate.class);
            GreetingService service =
                    context.getBean(GreetingService.class);

            System.out.println("definitions=" + definitions);
            System.out.println("injectedSame=" +
                    (service.template() == template));
            System.out.println("serviceSingleton=" +
                    (service == context.getBean(GreetingService.class)));
            System.out.println("greeting=" +
                    service.greet(" Lan "));
        }

        System.out.println("contextActiveAfterClose=" + context.isActive());
    }
}
~~~

**Runnability:** there is only one public top-level class `MinimalConfigDemo`; the other types are nested inside. `AppConfig` is declared as a `public static` nested class so Spring can use it as a configuration class. `greetingService(GreetingTemplate)` requires one collaborator, and the context has exactly one matching bean.

**Regarding `try (context)`:** Java 17 allows using an effectively final local variable as a resource, and Spring's `AnnotationConfigApplicationContext` can be closed via `close()`. After the block, `context.isActive()` returns `false`; do not continue retrieving or using beans from a closed context.

### 4.3. Maven Run Command and Expected Output

In the `minimal-spring-config` directory:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

**Five stdout lines printed by the application's `main` method on success:**

~~~text
definitions=true
injectedSame=true
serviceSingleton=true
greeting=Xin chao, Lan!
contextActiveAfterClose=false
~~~

Meaning:

- `definitions=true`: the context registered **both application bean names**. Do not infer the total number of bean definitions in the context is only two (there may be infrastructure definitions).
- `injectedSame=true`: the template reference held by the service is the exact `GreetingTemplate` bean supplied by the context.
- `serviceSingleton=true`: retrieving the `GreetingService` bean twice from the same context returns the same instance under the default singleton scope.
- `greeting=...`: behavior from regular Java service/template methods, not an annotation magically generating a greeting.
- `contextActiveAfterClose=false`: the context is no longer active after closing.

Output from `java -version`, `javac -version`, `mvn -version`, and any auxiliary Maven logs are not part of the five application stdout lines. Reference `==` checks are used deliberately to prove **singleton identity in this configuration**, not as a rule for every scope or proxy.

### 4.4. Compiling Manually with javac / Running with java

The code uses Spring, so the related JARs must be on the classpath. Generate the classpath list from Maven:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

Linux/macOS (bash or zsh):

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -cp "$(cat classpath.txt)" \
  -d out src/main/java/demo/MinimalConfigDemo.java
java -cp "out:$(cat classpath.txt)" demo.MinimalConfigDemo
~~~

Windows PowerShell:

~~~powershell
$deps = (Get-Content -Raw classpath.txt).Trim()
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -cp "$deps" -d out src/main/java/demo/MinimalConfigDemo.java
java -cp "out;$deps" demo.MinimalConfigDemo
~~~

In classpaths, Unix separates entries with `:`, while Windows uses `;`. `javac --release 17` compiles targeting Java 17 APIs/language; the launcher runs class `demo.MinimalConfigDemo`. If you encounter `package org.springframework... does not exist`, the first thing to check is **classpath/dependencies**, not “Spring failed to inject.”

## 5. What Did Spring Do at Startup?

The container receives `AppConfig.class` at initialization:

~~~java
new AnnotationConfigApplicationContext(AppConfig.class)
~~~

This snippet is extracted from the demo file, used when creating the context. Logically:

1. Spring processes `@Configuration` and registers bean definitions declared with `@Bean` (along with needed infrastructure definitions).
2. When creating singleton `greetingTemplate`, the factory method returns `VietnameseTemplate`.
3. When creating singleton `greetingService`, Spring sees the factory method requires `GreetingTemplate`, resolves the matching bean, and passes it in.
4. The factory method constructs `GreetingService(template)`. The service keeps that reference in its `final` field.
5. The application retrieves the service via `context.getBean(GreetingService.class)` and calls `greet(" Lan ")`.
6. When closing the context, Spring runs appropriate destroy/close callbacks on managed singletons. In this demo, neither service nor template holds I/O resources.

~~~mermaid
sequenceDiagram
    participant Main as main
    participant Context as SpringContext
    participant Config as AppConfig
    participant Template as GreetingTemplate
    participant Service as GreetingService
    Main->>Context: new Context(AppConfig.class)
    Context->>Config: process @Configuration / @Bean
    Context->>Config: greetingTemplate()
    Config-->>Context: VietnameseTemplate
    Context->>Config: greetingService(template)
    Config-->>Context: GreetingService
    Main->>Context: getBean(GreetingService.class)
    Context-->>Main: singleton service
    Main->>Service: greet(" Lan ")
    Service->>Template: render("Lan")
    Template-->>Service: "Xin chao, Lan!"
    Main->>Context: close()
~~~

This is an **illustrative dependency-flow model**, not a logger specification or a claim that all beans share this exact order. The ordering between these two beans comes from their dependency relationship: the service needs the template. Two independent beans have no universal fixed initialization order based on method names.

**BeanFactory vs. ApplicationContext:** `BeanFactory` is the foundational interface for accessing beans; `ApplicationContext` extends it with lifecycle, message resources, application events, and other conveniences. Real applications typically choose `ApplicationContext`. Spring does not require services to depend directly on `ApplicationContext`; the service only needs `GreetingTemplate`.

## 6. Default @Configuration vs. proxyBeanMethods=false

You may see two declaration styles:

~~~java
@Configuration
class DefaultConfig {
    @Bean
    GreetingTemplate greetingTemplate() {
        return new VietnameseTemplate();
    }

    @Bean
    GreetingService greetingService() {
        return new GreetingService(greetingTemplate());
    }
}
~~~

This is **non-standalone illustrative code**. By default, `@Configuration` has `proxyBeanMethods=true`: Spring enhances/intercepts eligible calls between `@Bean` methods within the managed configuration to preserve bean semantics such as singleton identity.

In our runnable demo, we used:

~~~java
@Configuration(proxyBeanMethods = false)
class AppConfig {
    @Bean
    GreetingTemplate greetingTemplate() {
        return new VietnameseTemplate();
    }

    @Bean
    GreetingService greetingService(GreetingTemplate template) {
        return new GreetingService(template);
    }
}
~~~

In `proxyBeanMethods=false` mode, a **direct** call from one factory method to another `@Bean` method is an ordinary Java method call and is **not intercepted** to return the scoped bean. For example:

~~~java
@Bean
GreetingService wrongStyle() {
    return new GreetingService(greetingTemplate());
}
~~~

If the configuration uses `false`, `greetingTemplate()` here runs like a plain Java method and can create a different object from the `greetingTemplate` bean in the context. That breaks expectations of a shared collaborator, especially when the template holds state or resources.

**Beginner-friendly choice:** pass dependencies via factory method parameters, as in `greetingService(GreetingTemplate template)`; Spring resolves the bean automatically. This makes dependencies explicit and avoids calling other factory methods directly. Do not set `proxyBeanMethods=false` blindly if your configuration relies on inter-bean method calls.

## 7. Bean Names, Types, Scopes, and Variants

By default, `@Bean` uses the method name:

~~~java
@Bean
GreetingService greetingService(GreetingTemplate template) { ... }
~~~

This is a **signature pattern**, not compilable Java source verbatim because of the `...`. In real code, the method body must return an appropriate object.

You can specify a different name:

~~~java
@Bean("greetingServicePrimary")
GreetingService buildGreetingService(GreetingTemplate template) {
    return new GreetingService(template);
}
~~~

Then `getBean("greetingServicePrimary")` looks up by the new name; do not confuse the **Java method name**, the **bean definition name**, and the **`GreetingService` type**. Only keep one properly named/registered method in a given configuration, and avoid pasting extra snippets into the demo causing duplicate registrations.

Some lookup APIs:

~~~java
GreetingService s1 = context.getBean(GreetingService.class);
Object s2 = context.getBean("greetingService");
boolean exists = context.containsBeanDefinition("greetingService");
~~~

This is a **snippet** assuming a valid `context` variable; type lookup must resolve unambiguously. With only one `GreetingService` in the demo, `getBean(GreetingService.class)` succeeds.

### Scope Is Not the Same as static

- `singleton` is the default scope: one bean instance per bean definition within one context, aside from special proxy/mechanism nuances affecting identity.
- `prototype` can create a new instance when requested appropriately. If you inject a prototype into a singleton normally, the dependency is resolved when the singleton is created, rather than automatically changing on every method call.
- `@Lazy` can defer instantiation until needed; it does not remove logical dependencies.
- Request/session scopes require a corresponding web environment; the plain Java project here does not include them.

Do not equate a singleton bean with a **class holding static fields** or a JVM-wide global instance. Two Spring contexts can hold two distinct singletons for the same logical bean definition.

## 8. Common Errors and How to Diagnose Them

| Symptom | Reason | How to Check |
| --- | --- | --- |
| `cannot find symbol` / `package org.springframework... does not exist` | Wrong name/import/classpath/compile dependency | Check JDK, Maven POM, `javac -cp`, package |
| Context cannot find `GreetingService` | Configuration class not loaded or lacks a valid `@Bean` method | Check `AppConfig.class` passed to context and method registration |
| `UnsatisfiedDependencyException` | Service needs a `GreetingTemplate` bean but no candidate exists | Register the collaborator or fix the factory parameter type |
| `NoUniqueBeanDefinitionException` | Two or more candidates for a single-value injection point | Choose with `@Qualifier`/`@Primary` or remove duplicate bean |
| `BeanCreationException` | Factory method, constructor, or init failed | Inspect `Caused by` and the failing method/class |
| `BeanCurrentlyInCreationException` | Unresolvable cycle in constructor/factory dependencies | Trace A→B→A and redesign dependencies |
| Service created via `new` outside context has no Spring lifecycle | Object is not managed by the container | Inject manually or retrieve the managed bean from context |
| Two beans of the same type from both `@Component` and `@Bean` | Unintended duplicate registration | Pick one mechanism or designate a clear candidate |
| `injectedSame=false` after edits | Direct call to `@Bean` method with `proxyBeanMethods=false` | Use a factory method parameter so Spring resolves it |
| `getBean` fails after context is closed | Using the container after shutdown | Use within context lifetime and close in the right place |
| Wrong greeting output even though context runs | Bug in Java logic or template data | Unit test the service/template; do not blame Spring for everything |

### Simple Negative Tests

1. **Missing bean:** delete or stop registering `@Bean GreetingTemplate greetingTemplate()` in a separate test configuration. Since `greetingService(GreetingTemplate)` requires that dependency, the context typically fails while creating the service. Observe the missing-bean error rather than inserting `null` to bypass it.
2. **Two candidates:** add two beans of type `GreetingTemplate` while keeping a single-valued injection point without qualifier/primary. If resolution yields no unique choice, Spring reports ambiguity. Note that name/qualifier/primary rules can still resolve some cases; do not claim having two beans always fails.
3. **Unregistered config:** keep a `@Configuration` class in source without passing, scanning, or importing it into the context. Annotations alone do not materialize beans.
4. **Renamed method:** a lookup by name may fail even when lookup by type still works. Check the exact actual bean name.

Keep negative experiments separate from the happy-path project. Do not rely verbatim on full stack trace text, as wording and wrappers can vary across JDK/Spring/config versions.

### Reading Errors from the Root Cause

An error on the service may simply be a downstream effect of a template factory method failing. In the exception chain, identify the bean name, injection point, factory method, and **first meaningful root cause**. If `mvn` fails to download dependencies, it has not reached bean wiring yet. If `javac` reports missing Spring packages, it has not reached context annotation processing yet.

## 9. Testing Logic and Testing Configuration

**Plain Java unit test:** use a fake template, no Spring needed:

~~~java
GreetingTemplate fake = name -> "TEST: " + name;
GreetingService service = new GreetingService(fake);
System.out.println(service.greet(" An ")); // TEST: An
~~~

This is an illustrative snippet within scope of the nested types, not a standalone file. It proves the service can use any collaborator supplied by the caller.

**Spring wiring smoke test:** initialize the context with the real configuration, retrieve beans, and verify references:

~~~java
try (AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext(AppConfig.class)) {
    GreetingTemplate expected = context.getBean(GreetingTemplate.class);
    GreetingService actual = context.getBean(GreetingService.class);
    if (actual.template() != expected) {
        throw new IllegalStateException("unexpected injection");
    }
}
~~~

This is also a snippet placed inside a method/class with proper imports and access. It verifies **container configuration**, without proving all business behaviors or runtime environments are valid.

A passing unit test does not prove Spring registered the bean; conversely, a successful context refresh does not prove greeting logic is correct. In real projects, put both groups into automated tests (e.g., JUnit/Spring Test) as the codebase grows.

### Do Not Use Java assert for Mandatory Checks

Java `assert` is disabled by default unless `-ea` is enabled. When the goal is to **enforce detection of bad wiring** in tests or applications, use test framework assertions or explicit conditional checks throwing exceptions. This demo prints boolean values for observation; in serious systems, **fail the test** when values are wrong rather than logging and continuing.

## 10. Exercises with Answers

**Exercise 1.** How is `@Bean GreetingService greetingService(GreetingTemplate template)` invoked when there is only one bean of type `GreetingTemplate`?

**Answer:** Spring resolves the matching bean according to type/injection rules, passes it as the factory method parameter, and invokes the method to obtain the service. You do not call `greetingTemplate()` yourself.

**Exercise 2.** If `@Bean greetingService(...)` is already defined, do you also need `@Component` on `GreetingService`?

**Answer:** No. `@Bean` already registers the factory creating the service; unintentionally adding scanning could create duplicate candidates or ambiguity.

**Exercise 3.** Why is `serviceSingleton=true` in the demo?

**Answer:** `@Bean` defaults to singleton scope within the same context. Calling `getBean(GreetingService.class)` twice returns the same instance, not because the class uses static fields.

**Exercise 4.** Does `@Configuration(proxyBeanMethods=false)` intercept `greetingTemplate()` when another method calls it directly?

**Answer:** No. When called directly, it executes as a plain Java call and may create an extra instance, which is why the standard example declares dependencies as method parameters.

**Exercise 5.** Can you create a Spring app using just `new AnnotationConfigApplicationContext(AppConfig.class)` without Spring Boot?

**Answer:** Yes. This is pure Spring Framework Core Container; the `spring-context` module, Java configuration, and JDK/Maven suffice for this example.

**Exercise 6.** Why is `context.containsBeanDefinition("greetingService")` better than asserting the entire context has only two bean definitions?

**Answer:** The context may also contain internal infrastructure definitions. Only the application's two `@Bean` methods should be checked by **target name**, not total definition count.

**Exercise 7.** Is an object created via `new GreetingService(new VietnameseTemplate())` outside the context a Spring bean?

**Answer:** No, it is an ordinary Java object, even though manual constructor injection is valid. It does not automatically receive container lifecycle or scope management.

## 11. Lesson Completion Checklist

- [ ] Using JDK 17+, Maven, and the `spring-context` module.
- [ ] Consistent `pom.xml`, package, filename, and public class name.
- [ ] `AppConfig` has `@Configuration` and is loaded into the context.
- [ ] Both factory methods use `@Bean` with clear names and types.
- [ ] `GreetingService` receives `GreetingTemplate` via constructor, without fetching beans from the context itself.
- [ ] `greetingService(GreetingTemplate)` uses a Spring-resolved parameter instead of calling `greetingTemplate()` directly.
- [ ] Understand default singleton scope and the effect of `proxyBeanMethods=false`.
- [ ] Run `mvn -q clean compile exec:java` and verify the 5 stdout lines.
- [ ] When running `javac`/`java` directly, supply all required Spring JARs on the classpath.
- [ ] Close the context when the app owns its lifecycle, and never use it after closing.
- [ ] Distinguish checks for registration, wiring, behavior, and classpath errors.
- [ ] Experiment with missing-bean, wrong-name, and unregistered-config cases in a separate test.

**Conclusion:** With `@Configuration`, Spring knows the **configuration source**; with `@Bean`, Spring knows the **factory method supplying an object**. `AnnotationConfigApplicationContext` processes metadata, resolves parameter dependencies, creates/retains beans by scope, and lets the application retrieve them. You now have your first Spring Core Container application **without needing Spring Boot**.

### Official Spring Documentation

- [Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html)
- [Using @Bean](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
- [Using @Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java/configuration-annotation.html)
- [Dependency Injection and Collaborators](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
