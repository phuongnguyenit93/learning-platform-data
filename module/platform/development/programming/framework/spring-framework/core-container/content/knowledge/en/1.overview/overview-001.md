# What Is the Core Container and Where Does It Sit in Spring Framework?

## 1. Short Answer: Spring's Foundational Object Management Layer

**Spring Core Container** is the foundational group of modules and mechanisms that enables a Java application to **declare, create, wire, configure, and manage the lifecycle of objects managed by Spring**. These container-managed objects are called **Spring beans**. Its most prominent part is the **IoC container** (*Inversion of Control container*), typically accessed through the `ApplicationContext` interface.

Instead of each object locating or instantiating all of its collaborators on its own, the application describes what it depends on; the container reads the configuration and **provides the dependencies (Dependency Injection – DI)** when creating beans. As a result, business code is less tightly coupled to instantiation details and components are easier to swap during testing.

A simple distinction:

- **Core Container**: the foundational layer in Spring Framework, consisting of multiple modules and APIs; it is not the name of a single Java class.
- **IoC container**: the concrete mechanism that reads metadata, manages beans, and wires dependency relationships.
- **Bean**: an object managed by the container; simply using the `new` keyword in Java does not automatically make an object a Spring bean.
- **DI**: a way of implementing IoC in which dependencies are passed into an object rather than the object locating or creating its dependencies itself.

For example, `OrderService` needs an `OrderRepository`. If `OrderService` creates `new JdbcOrderRepository(...)` itself, the service class directly knows about instantiating the implementation. With DI, `OrderService` receives an `OrderRepository` via its constructor; the container selects and supplies an appropriate bean according to the configuration.

**Do not equate the container with a web server.** You can create an `ApplicationContext` in a console Java program, a batch application, or a process that does not use HTTP.

## 2. Where Does the Core Container Sit in Spring Framework?

Spring Framework is a collection of multiple **modules (artifacts/JARs)** with different responsibilities. The Core Container sits **at the center/foundation of the application model**, providing object management capabilities for the other parts to use:

~~~text
                     JAVA APPLICATION
                (console, batch, web, ...)
                            |
     +----------------------+----------------------+
     |                      |                      |
   Spring MVC/           Data Access/          Spring AOP/
   Spring WebFlux         Transaction           Messaging/...
     |                      |                      |
     +----------------------+----------------------+
                            |
                CORE CONTAINER (IoC/DI)
                   BeanFactory / Context
                            |
           spring-core, spring-beans,
           spring-context, spring-expression
                            |
                           JVM
~~~

This diagram is a **conceptual diagram of roles**, not an absolute Maven dependency graph: each module has its own technical dependencies, and not every application needs all the upper parts. For example, `spring-webmvc` handles HTTP requests while still relying on `ApplicationContext` to obtain controllers, services, and other beans. AOP and transactions are typically **integrated through bean/proxy mechanisms** rather than the IoC container automatically enabling all of those behaviors on its own.

**Spring Framework differs from Spring Boot:**

- **Spring Framework** provides the DI/IoC foundation along with web, data, transaction, AOP, and other modules that an application chooses from.
- **Spring Boot** builds **on top of Spring Framework**, making configuration, startup, dependency management, and auto-configuration more convenient. Boot **uses the Core Container** rather than replacing it with an independent IoC mechanism.
- `@SpringBootApplication` is a Boot convenience annotation and is **not required** to use a plain Spring Framework `ApplicationContext`.
- Having the Core Container does not mean an HTTP server, REST endpoints, a database, transactions, or Spring Security are ready out of the box. Those require the appropriate modules, configuration, and conditions.

The example in this lesson uses **Spring Framework directly**, without Boot and without a web server.

## 3. Core Layer Modules and Their Main Responsibilities

| Artifact/module | Easy-to-remember role | Example APIs/features |
| --- | --- | --- |
| `spring-core` | Core utilities and infrastructure for the Framework | `Resource`, type conversion, foundational utilities |
| `spring-beans` | Bean model, metadata, and the foundation of IoC | `BeanFactory`, `BeanDefinition`, dependency wiring |
| `spring-context` | Application-level container and accompanying features | `ApplicationContext`, annotation configuration, events, i18n |
| `spring-expression` | Spring Expression Language (SpEL) | `#{...}` expressions in supported contexts |
| `spring-context-support` | Additional supporting integrations around the context | Specialized adapters/integrations, **not** a required step for simple DI examples |

The module grouping can be explained differently depending on the documentation diagram and Spring version; the first four artifacts are the parts most commonly mentioned when learning IoC. `spring-context-support` is an **optional supporting module based on need** and does not need to be added just to write `@Bean`.

Maven artifact names look like `spring-context`, whereas Java packages like `org.springframework.context` are **source code namespaces**; do not confuse Java packages with Maven JARs or with **JPMS modules** (`spring.context`). When you add the `spring-context` dependency via Maven/Gradle, other required modules are typically pulled in **as transitive dependencies**, so you do not necessarily have to declare each JAR manually.

Spring also has other modules (`spring-web`, `spring-webmvc`, `spring-jdbc`, `spring-tx`, `spring-aop`, `spring-test`, ...). They provide specialized capabilities and are **not synonymous** with `spring-core` or the entire Core Container.

## 4. IoC/DI Mechanism: What Does Spring Manage?

A condensed lifecycle of an application using a context:

~~~text
Configuration (annotations / @Bean / XML / programmatic registration)
                         |
                         v
            Container reads bean metadata
                         |
                         v
      Determines how to create and wire dependencies
                         |
                         v
     Creates beans, injects dependencies, initializes
                         |
                         v
    Application retrieves or receives beans to use
                         |
                         v
       Closes context, destroys eligible beans
~~~

A **bean definition** is the **description/configuration** of a bean: type, name, scope, dependencies, creation method, callbacks, etc. A bean instance is the **actual object** after creation. One bean definition does not always equal one immediate object: scope and initialization policy affect when and how many times it is created.

Three common ways to provide configuration:

1. **Java configuration**: `@Configuration` and `@Bean` factory methods declare beans; dependencies are very easy to see via factory method parameters.
2. **Component scanning**: `@Component`, `@Service`, `@Repository`, `@Controller`, and `@ComponentScan` when appropriate so Spring discovers components and registers beans.
3. **XML or programmatic registration**: applications can still use `ClassPathXmlApplicationContext`, `GenericApplicationContext`, or direct bean registration APIs.

**Simply adding `@Component` to a class does not make a bean appear automatically**: that class must be included in an appropriate configuration/scan source. Similarly, if an object is created manually with `new` outside the context, DI annotations on it are not automatically processed by Spring.

The most common DI style for required dependencies is **constructor injection**:

~~~java
// Plain Java illustration, placed in appropriate types.
interface EmailSender {
    void send(String message);
}

class NotificationService {
    private final EmailSender sender;

    NotificationService(EmailSender sender) {
        this.sender = sender; // Dependency provided by caller/container.
    }

    void notifyUser() {
        sender.send("Ready");
    }
}
~~~

Because `NotificationService` accepts an interface, during testing you can pass a mock/fake implementation (*fake*) without modifying the service's logic. Constructor injection does not exist only in Spring: it is also a plain Java design technique; **Spring automates creating/supplying objects** based on configuration.

## 5. `BeanFactory` and `ApplicationContext`: Understanding Their Roles Properly

| Criterion | `BeanFactory` | `ApplicationContext` |
| --- | --- | --- |
| Role | Foundational interface for accessing/managing beans | Application-oriented container interface, **extending** `BeanFactory` |
| Prominent APIs | `getBean(...)`, inspecting bean metadata | Includes `BeanFactory` APIs; adds events, resources, messages/i18n, and other utilities |
| Usage in new apps | Usually no need to interact with directly | **Common choice** for bootstrapping Spring |
| Singleton instantiation timing | Depends on implementation/bootstrap configuration | Typically instantiates **non-lazy** singletons on context refresh |
| Example implementations | `DefaultListableBeanFactory` | `AnnotationConfigApplicationContext`, `ClassPathXmlApplicationContext` |

`ApplicationContext` is **a kind of `BeanFactory`**, not two separate containers you have to create independently. Features such as `BeanPostProcessor`, annotation processing, and lifecycle handling are activated through the proper bootstrap process; merely instantiating a bare `DefaultListableBeanFactory` and expecting all annotations to run automatically may not produce the expected results.

You should not generalize "`BeanFactory` is always lazy while `ApplicationContext` is always eager" as an absolute rule. Scope, lazy-init, and how an implementation is used determine the details; a safe way to state it is that `ApplicationContext` normally **pre-instantiates non-lazy singletons** during refresh.

## 6. Hands-On Plain Spring Core Container with Java 17+

This complete example demonstrates **the container creating beans and injecting a dependency via a `@Bean` parameter**, without Spring Boot, HTTP, or a database. **JDK 17+ and Maven 3.9+** are required (Maven will download libraries from the repository on the first run).

In a `core-container-demo` directory, create the structure:

~~~text
core-container-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── CoreContainerDemo.java
~~~

### 6.1. `pom.xml` – Declaring Spring Framework

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>core-container-demo</artifactId>
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
                    <mainClass>demo.CoreContainerDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Version **Spring Framework 7.0.9** is pinned in this example so everyone runs the same version; this is a 7.0-line release that supports **Java 17 as a baseline**, although the Spring 7 line recommends a newer LTS JDK for suitable projects. In real projects, follow your dependency/BOM management policy and update to supported patch releases rather than keeping this learning version indefinitely.

### 6.2. `src/main/java/demo/CoreContainerDemo.java`

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class CoreContainerDemo {
    private CoreContainerDemo() {
    }

    interface MessageRepository {
        String prefix();
    }

    static final class FixedMessageRepository implements MessageRepository {
        @Override
        public String prefix() {
            return "Xin chao";
        }
    }

    static final class WelcomeService {
        private final MessageRepository repository;

        WelcomeService(MessageRepository repository) {
            this.repository = repository;
        }

        String greet(String name) {
            return repository.prefix() + ", " + name + "!";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {
        @Bean
        MessageRepository messageRepository() {
            return new FixedMessageRepository();
        }

        @Bean
        WelcomeService welcomeService(MessageRepository repository) {
            return new WelcomeService(repository);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            WelcomeService service = context.getBean(WelcomeService.class);

            System.out.println("message=" + service.greet("Lan"));
            System.out.println("hasBean="
                    + context.containsBean("welcomeService"));
            System.out.println("sameSingleton="
                    + (service == context.getBean(WelcomeService.class)));
            System.out.println("contextType="
                    + context.getClass().getSimpleName());
        }
    }
}
~~~

**Run in the directory containing `pom.xml`:**

~~~bash
java -version
mvn -version
mvn -q compile exec:java
~~~

The Maven Compiler Plugin compiles the code with `--release 17` per the declared property. Maven handles the **classpath containing Spring and transitive dependencies**, so running `javac`/`java` manually without setting up the classpath for Spring JARs will report missing packages/classes. The command `mvn -q compile exec:java` both compiles via `javac` through the plugin and launches the main class.

**Stdout from the application's four `System.out.println` statements** (excluding version info from the two environment check commands, and excluding logs/diagnostics emitted outside the application by Maven or a logging backend):

~~~text
message=Xin chao, Lan!
hasBean=true
sameSingleton=true
contextType=AnnotationConfigApplicationContext
~~~

This is the deterministic stdout of the example logic: a bean named `welcomeService` is registered by the factory method of the same name; by default the bean has **singleton scope** in the context, so retrieving the same type twice returns the same instance. If your IDE/logging prints extra information to the console, distinguish it from the four lines printed by the program itself.

### 6.3. Tracing Each Step in the Example

1. `new AnnotationConfigApplicationContext(AppConfig.class)` creates the context, registers the configuration class, and performs bootstrap/refresh in this constructor form.
2. `@Configuration` marks `AppConfig` as a source of bean definitions; `proxyBeanMethods=false` selects the appropriate handling when **not relying on calling one `@Bean` method directly from another**.
3. `@Bean messageRepository()` creates the `MessageRepository` bean using `FixedMessageRepository`.
4. `@Bean welcomeService(MessageRepository repository)` asks Spring to **resolve the parameter** from a matching bean type, then passes it into the `WelcomeService` constructor. The `welcomeService` method **does not call** `messageRepository()` directly and does not hard-code the dependency inside the service.
5. `getBean(WelcomeService.class)` looks up the managed bean; calling `greet("Lan")` afterward is a normal Java method call on the returned instance.
6. `containsBean("welcomeService")` verifies that the bean name exists in the current context.
7. `try-with-resources` closes the context when exiting the block. Certain beans have lifecycle callbacks invoked by the container when the context closes; **general Java objects do not automatically vanish or get garbage-collected immediately on close**.

**Keep focus on the core point:** the service code does not import Spring; only the configuration class and the bootstrap section know about `ApplicationContext`. This is one way to keep business logic easy to test even when changing how the container is configured.

## 7. Not Every Object Is a Bean; Scopes and Lifecycles Have Boundaries

**`singleton` scope** is Spring's default scope: one bean definition typically corresponds to **one shared instance per container**. That is **not** a guarantee that only one object exists across the entire JVM or across multiple application contexts.

**`prototype` scope** typically creates a new instance each time the container is asked for that bean. Spring creates/configures it and invokes appropriate initialization callbacks, but **does not automatically manage all destruction callbacks for prototype beans after handing them to the caller**. Scopes like `request` or `session` also require an appropriate web context; they cannot be used by default in the console context shown in the example.

**Context-bound lifecycle**: A bean can participate in creation → injection → initialization → usage → destruction. `ApplicationContext.close()` handles lifecycle callbacks for beans within the appropriate management scope (especially singletons), rather than acting as a command to close every object ever created by code.

**Do not confuse these three situations:**

| Situation | Who creates/manages it? | Consequence |
| --- | --- | --- |
| `context.getBean(WelcomeService.class)` | Spring Core Container | Accesses a bean already registered by type |
| `new WelcomeService(repository)` in regular code | That code itself | Plain Java object; does not automatically get Spring DI/lifecycle |
| `new FixedMessageRepository()` inside a `@Bean` method | The method creates the object; Spring registers/manages the **returned** object | The returned object becomes a bean; not every intermediate object in the method becomes a bean |

A bean can depend on other beans and form a **dependency graph**. If a suitable bean is missing, multiple beans of the same type exist without a clear resolution rule, or there is an unresolvable constructor circular dependency, bootstrap may fail instead of creating an invalid graph.

## 8. When to Use the Core Container, and When Do You Need Other Modules?

**Use the Core Container when:**

- You need to manage multiple services/repositories/clients with clear dependencies.
- You want to swap implementations in tests and avoid scattering `new` for dependencies throughout business code.
- You need environment-specific object configuration and application-level lifecycle/extension points.
- You are building a layered console, batch, service, or web application.

**You may not need a container yet** if you are only writing a small Java program with a few pure functions and no significant dependency graph; instantiating objects directly may be simpler and more appropriate.

**When your goals expand:**

| What do you want to do? | Relevant part | Note |
| --- | --- | --- |
| Bean coordination, DI, configuration | Core Container | Primary scope of this lesson |
| Building REST/MVC web apps | Spring Web/Spring MVC or WebFlux | Must add the corresponding modules/configuration |
| SQL, transactions | Spring JDBC/`spring-tx`, data integration | DI provides dependencies; it does not automatically perform transactions |
| Proxies and cross-cutting advice | Spring AOP and corresponding configuration | Spring does not automatically turn every method call into advice |
| Auto-configuration, executable apps | Spring Boot | Boot builds on Spring Framework's Core Container |
| Integration testing the bean graph | Spring Test | Can spin up a context in tests, but you must control scope and startup cost |

Spring Core Container is the **foundation for many features**, not the entirety of enterprise capabilities enabled by default.

## 9. Common Misconceptions and How to Self-Check

1. **"IoC = DI completely."** DI is one way of applying the IoC principle. When learning Spring, you often see IoC realized through DI and container object management.
2. **"Adding `spring-core` gives you the full `ApplicationContext`."** No. The application-level container lives in `spring-context`; Maven will manage related dependencies when you declare the right artifact.
3. **"Putting `@Component` on a class makes Spring manage it everywhere."** Only when the class is within the scan/registration source of an appropriate context.
4. **"`@Bean` is an annotation placed on a class."** Most commonly, `@Bean` is placed on a **factory method** inside a configuration class; `@Component` is what is used on a class for scanning.
5. **"DI requires `@Autowired` on fields."** Constructor injection or factory-method parameter injection is usually clearer and easier to test; when a managed component has a single constructor, Spring can inject it without `@Autowired`.
6. **"Spring's singleton means one instance across all contexts."** By default it is **one instance per bean definition per context**; creating another context can produce a different object.
7. **"Having an `ApplicationContext` makes a web server start automatically."** False. The console example above does not open an HTTP port.
8. **"The container creates beans anyway even when configuration is wrong."** Missing dependencies, ambiguity among multiple candidates, or an unresolvable graph can cause startup to fail.
9. **"Calling `close()` destroys every Java object."** False. The context invokes appropriate lifecycle callbacks; Java GC and reference lifetimes have their own mechanisms.
10. **"Spring Boot and Spring Framework are the same thing."** Boot uses Framework and adds bootstrap, auto-configuration, and developer utilities; understanding the Core Container helps you understand Boot clearly.

### Verification Exercises

- **Exercise A – swap implementation:** add `AnotherMessageRepository` and change the return value in the `messageRepository()` factory method. Predict only the `message=...` line before running.
- **Exercise B – scope:** apply `@Scope("prototype")` to the `welcomeService` bean, retrieve the bean twice, and check `==`. Predict why `sameSingleton` becomes `false` (you should rename the printed label to `sameInstance` for accuracy).
- **Exercise C – missing dependency:** temporarily remove the `messageRepository()` factory method and run again. Inspect the exception type when the context cannot resolve the `MessageRepository` parameter. Do not copy an exact exception message verbatim, as it may vary across versions.
- **Exercise D – separate configuration:** move `AppConfig` into its own file, keep `WelcomeService` plain Java, and verify the output does not change.
- **Exercise E – compare:** create `WelcomeService` manually with `new` and place it alongside the context-managed version. Point out where the dependency is chosen, who owns the lifecycle, and when each approach should be used.

Each exercise is **an independent change**; restore the original code to re-run the baseline stdout in section 6.

## 10. Key Takeaways and Official Documentation

- The Core Container is **the foundational layer of Spring Framework**, not a synonym for Spring Boot or Spring MVC.
- Core role: **managing beans and their dependencies** according to configuration, providing IoC/DI and appropriate lifecycles.
- `BeanFactory` is the foundational API and `ApplicationContext` extends it for applications; in practice you usually start with `ApplicationContext`.
- Key modules: `spring-core`, `spring-beans`, `spring-context`, `spring-expression`; `spring-context-support` adds integrations when needed.
- A program **that does not use HTTP** can still create a context. What matters is that the object graph is assembled and put to use according to its contracts.

Documentation for checking APIs and version-specific behavior:

- [Spring Framework Overview](https://docs.spring.io/spring-framework/reference/overview.html)
- [Spring IoC Container and Beans](https://docs.spring.io/spring-framework/reference/core/beans/introduction.html)
- [Container Overview](https://docs.spring.io/spring-framework/reference/core/beans/basics.html)
- [Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Spring Framework 7.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes)

**Conclusion:** The Core Container is where Spring **organizes and wires application objects together**. Understanding the container's position, responsibilities, and boundaries will help you continue learning bean configuration, component scanning, injection, scopes/lifecycle, AOP, transactions, and Spring Boot without confusing the layers.