# Prerequisite Knowledge of Java 21, IoC, and Spring Boot 3.3

## 1. Goal and big picture

Before studying **Spring Boot Application Runtime**, you need to grasp three supporting layers of knowledge:

- **Java 21 and the JVM:** write, compile, and run programs; understand data types, object-oriented programming, exceptions, collections, threads, and resource management.
- **Spring Framework and IoC/DI:** understand why an object can be created, configured, wired with dependencies, and lifecycle-managed by Spring.
- **Spring Boot 3.3:** understand how a Spring application starts up, selects default configuration from the classpath, reads external configuration, and launches an embedded web server when needed.

Distinguish the three roles:

| Concept | Responsibility | Question to answer |
| --- | --- | --- |
| Java 21 | Language, standard library, JVM, program execution threads | How is code compiled and executed? |
| Spring IoC container | Creates and manages `bean`s, injects dependencies, invokes lifecycle points | Who creates `Service` and provides `Service` to `Controller`? |
| Spring Boot 3.3 | Collection of starters, auto-configuration, bootstrap, and utilities for running the app | Why does adding the web starter let you run an HTTP server without setting up Tomcat manually? |

**Expected outcome:** be able to run a small Java 21 application on your own, explain the dependency diagram `Controller -> Service`, understand why `@SpringBootApplication` initializes an `ApplicationContext`, and troubleshoot common setup errors yourself.

## 2. Environment setup and understanding versions accurately

Spring Boot **3.3.x requires at least Java 17**; using **JDK 21** is a good choice for learning Java 21 features at the same time. The Spring Boot 3.3 line is based on Spring Framework 6.1 and uses the `jakarta.*` ecosystem instead of many older Java EE `javax.*` APIs. For a typical Spring MVC application, the web starter provides an embedded Servlet server (Tomcat by default).

Preparation:

1. Install **JDK 21**, and set `JAVA_HOME` and executable paths consistently across your IDE, terminal, and build tools.
2. Install **Maven 3.6.3+** (or a Gradle version supported by Spring Boot 3.3); prefer the Maven/Gradle Wrapper included in the project.
3. Use an IDE that supports Java 21, Maven/Gradle, and running/debugging Java applications.
4. Check `java -version`, `javac -version`, `mvn -version`; all three commands should point to the expected version. If the IDE compiles with JDK 21 while the terminal runs an older JRE/JDK, errors will still occur.
5. Understand **dependency**, **transitive dependency**, **classpath**, JAR artifacts, and how a dependency management/BOM keeps libraries mutually compatible.

Environment check example:

```bash
java -version
javac -version
mvn -version
```

The commands print machine-dependent version information; there is no single fixed output. In real projects, choose the appropriate patch release within the required branch according to the project's maintenance policy; the hands-on example below pins `3.3.13` to ensure reproducibility.

## 3. Java foundations to know before writing Spring

### 3.1. Syntax, data types, and object-oriented programming

- Distinguish **primitive** (`int`, `boolean`, `long`, etc.) from **reference** types; understand `null`, boxing/unboxing, and the risk of `NullPointerException`.
- Distinguish **class**, **interface**, **abstract class**, inheritance, and composition. In application design, generally prefer composition and depend on interfaces when multiple implementations are needed.
- Understand access modifiers `private`/`protected`/`public`, constructors, `final`, `static`; avoid treating `static` as a holder of shared application-wide state.
- Know how **method overloading** differs from **overriding**, how `equals`/`hashCode` work when using objects as map keys, and why mutable state makes testing and multithreading harder.
- Know **checked** vs. **unchecked** exceptions, how to propagate the cause when rethrowing exceptions, and how to close resources with `try-with-resources`.

### 3.2. Collections, generics, lambdas, and Streams

- `List` preserves order and allows duplicate elements; `Set` represents a collection of unique elements; `Map` maps keys to values. Understand basic operations and the significance of `equals`/`hashCode`.
- **Generics** provide compile-time type checking: `List<String>` is not `List<Object>`. With wildcards, a quick rule of thumb is "producer extends, consumer super" where appropriate.
- **Lambdas/method references** are ways to pass behavior as a functional interface; distinguish captured variables from mutable data fields.
- A `Stream` typically has a source, intermediate operations (`filter`, `map`), and a terminal operation (`toList`, `collect`). Streams **do not mutate** the source data in place; do not rely on the arbitrary iteration order of `HashMap`/`HashSet`.

### 3.3. Java 21 features worth recognizing

- **Record** represents a data-carrying type, auto-generating accessors, `equals`, `hashCode`, and `toString`; record state is **shallowly immutable**, meaning it does not turn a mutable `List` inside into an immutable one.
- **Pattern matching for `switch`** and `switch` expressions support type-based handling; in Java 21, this feature is standard and requires no preview flag.
- **Sealed classes/interfaces** allow restricting the set of direct implementations according to declared rules.
- **Virtual threads** (finalized in Java 21) are useful when many tasks mostly **wait on I/O**. They do not speed up CPU computation by themselves, do not remove connection pool limits, and still require resource control.
- `var` only infers **local variable types at compile time**; Java remains a statically typed language.

A standalone Java 21 program, without Spring libraries:

**File `Java21Check.java`**

```java
import java.util.List;

record Candidate(String name, int score) {}

public class Java21Check {
    static String describe(Object value) {
        return switch (value) {
            case Integer n when n >= 0 -> "nonnegative: " + n;
            case Integer n -> "negative: " + n;
            case String s -> "text: " + s;
            case null -> "null";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        Candidate candidate = new Candidate("Lan", 9);
        List<String> names = List.of("An", "Lan", "Binh").stream()
                .filter(name -> name.length() <= 3)
                .map(String::toUpperCase)
                .toList();

        System.out.println(candidate.name() + ":" + candidate.score());
        System.out.println(describe(21));
        System.out.println(names);
    }
}
```

Compile and run with JDK 21:

```bash
javac Java21Check.java
java Java21Check
```

Standard output:

```text
Lan:9
nonnegative: 21
[AN, LAN]
```

The program demonstrates records, collections/Streams, and pattern matching for switch. `filter` keeps `An` and `Lan` because their length is at most 3; `Binh` has 4 characters and is filtered out. `toList()` creates a result list without modifying the original `List.of(...)`.

### 3.4. Essential JVM and runtime knowledge

Understand the path **`.java -> javac -> .class (bytecode) -> JVM`**. The JVM uses class loaders to load classes, executes bytecode (interpretation/JIT), allocates the heap, uses stacks for call frames, and performs garbage collection as appropriate. `OutOfMemoryError`, class-loading errors, and deadlocks differ from syntax errors; you need to know how to read a stack trace down to the **root cause**.

Distinguish **process** from **thread**; recognize issues around shared mutable state, race conditions, blocking I/O, and timeouts. A web application can handle many requests concurrently, so singleton beans should not hold per-request data in mutable fields.

## 4. IoC and Dependency Injection: the foundation of Spring

### 4.1. What is IoC?

**Inversion of Control (IoC)** means that responsibility for creating, wiring, and managing objects is handed over to a coordinating component — in Spring, the **IoC container** (typically `ApplicationContext`). Instead of a controller creating every dependency itself with `new`, the container supplies configured objects.

**Dependency Injection (DI)** is a technique for implementing IoC: dependencies are **passed into** the object that needs them. DI is not entirely synonymous with IoC; Spring also manages bean lifecycles, scopes, configuration, and many other services.

Picture a dependency chain:

```text
HTTP request
    |
    v
GreetingController --constructor injection--> GreetingService
                               ^
                               |
                     Spring ApplicationContext
                     creates and provides beans
```

If `GreetingController` calls `new GreetingService()` itself, the controller is tightly coupled to how the service is instantiated. If it receives the service via its constructor, you can swap in another implementation or a fake in tests without changing the controller's logic.

### 4.2. Beans, container, and registration methods

A **bean** is an object managed by the Spring container. Common registration methods:

- `@Component` for a general Spring component; `@Service`, `@Repository`, and `@Controller` are role-based stereotypes discoverable by component scanning.
- `@RestController` combines controller behavior with writing return values directly into the HTTP response body.
- `@Configuration` paired with `@Bean` methods is useful when instantiating objects from third-party libraries or when you want explicit control over initialization.
- `@Import`, conditional configurations, and auto-configuration can add beans; **merely putting an annotation on a class does not guarantee that the class is scanned or imported**.

Example of declaring a bean for a standard library class (placed in a scanned package):

```java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TimeConfiguration {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

Here `Clock` is a bean provided by the `clock()` method; other beans can receive `Clock` via constructor injection. The example above is **an additional class for a Spring project**, not a standalone `javac` program because it requires Spring libraries.

### 4.3. Constructor injection and handling multiple implementations

Prefer **constructor injection** for required dependencies:

```java
@Service
class BillingService {
    private final PaymentGateway gateway;

    BillingService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

The snippet above only illustrates the design pattern; `PaymentGateway` and the `@Service` import must exist in a real project. For a class with only **one constructor**, Spring does not require `@Autowired` on that constructor.

If the container finds **multiple beans of the same type**, disambiguate using `@Qualifier`, `@Primary`, or by redesigning the extension point. If no matching bean exists, context startup can fail. A missing required dependency should not be "fixed" by calling `new` directly inside a controller, as that bypasses container management and configuration.

**Lifecycle and scope:** by default beans have `singleton` scope — **one instance per Spring container**, not meaning a single instance across the entire JVM. `prototype` creates a new instance on each request for the bean; web applications have additional scopes such as `request`. The container handles instantiation, dependency injection, and callbacks such as `@PostConstruct` and `@PreDestroy` for eligible beans (on Spring 6, using `jakarta.annotation.*`). Do not store per-request state in a mutable singleton.

**Advanced caveats to recognize:** circular dependencies make initialization difficult; proxy-based features like `@Transactional` have limitations on self-invocation within the same bean. You only need to recognize these as container mechanics here, without diving deep into implementation in this preparation lesson.

## 5. What does Spring Boot 3.3 add?

### 5.1. Spring Framework vs. Spring Boot

Spring Framework provides IoC/DI and modules such as Spring MVC, transactions, and data access. Spring Boot helps you **set up and run** Spring applications faster through:

- **Starter dependencies**: grouped libraries tailored to a need, such as `spring-boot-starter-web` or `spring-boot-starter-test`.
- **Auto-configuration**: configures beans based on libraries on the classpath, properties, and existing conditions; typically backs off in favor of application-configured beans when matching conditions apply.
- **`SpringApplication`**: bootstraps the `ApplicationContext`, prepares the environment, and runs the application.
- **Embedded servers** when using an appropriate web starter; packaged JARs can be started with `java -jar`.
- **Externalized configuration** via `application.properties` / `application.yml`, environment variables, command-line arguments, and supported configuration sources.

`@SpringBootApplication` combines three mechanisms: `@SpringBootConfiguration`, `@EnableAutoConfiguration`, and `@ComponentScan`. By default, component scanning starts from the **package containing the application class** and its subpackages. Therefore, placing the main class in the root package of your application helps Spring find controllers, services, and configurations.

### 5.2. Conceptual startup flow

```text
main()
  -> SpringApplication.run(...)
  -> Prepare Environment / configuration / profiles
  -> Create ApplicationContext, register configurations and bean definitions
  -> Component scan + conditional auto-configuration
  -> Instantiate, wire beans, and run appropriate lifecycle
  -> If web app: start embedded web server
  -> Application ready to accept requests
```

This is a **conceptual diagram**, not an absolute ordering of internal callbacks. When an HTTP request is sent to an MVC application, the web server passes the request into Spring MVC's processing chain (including `DispatcherServlet`), locates the matching handler, invokes the controller/service, and writes the response.

### 5.3. Configuration and profiles

A simple configuration:

**File `src/main/resources/application.yml`**

```yaml
spring:
  application:
    name: java21-ioc-boot33
server:
  port: 8080
```

File configuration establishes defaults; values can be **overridden** by higher-precedence sources, such as command-line arguments. For example, running on another port: `java -jar target/demo-0.0.1-SNAPSHOT.jar --server.port=8081`. `spring.profiles.active` selects the corresponding configuration profile, though profiles are not a secrets-management mechanism. For multiple related properties, prefer strongly typed configuration via `@ConfigurationProperties` with appropriate validation instead of scattering `@Value` throughout the codebase. Never commit secrets into the repository.

## 6. Complete hands-on practice: Java 21 + Spring Boot 3.3 + DI

This example uses no database, which is enough to observe the container instantiating a service and injecting it into a controller. Create a Maven project with this structure:

```text
demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/demo/
    │   │   ├── DemoApplication.java
    │   │   ├── GreetingService.java
    │   │   └── GreetingController.java
    │   └── resources/application.yml
    └── test/java/com/example/demo/
        └── GreetingServiceTest.java
```

**File `pom.xml`**

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
    <artifactId>demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

The Spring Boot parent manages common dependency and plugin versions; you do not need to specify versions manually for the two starters in the example. Spring Boot 3.3.13 belongs to the 3.3 line and is compatible with JDK 21. If a project already has its own BOM or parent, you must follow its existing version-management mechanism.

**File `src/main/java/com/example/demo/DemoApplication.java`**

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

**File `src/main/java/com/example/demo/GreetingService.java`**

```java
package com.example.demo;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

**File `src/main/java/com/example/demo/GreetingController.java`**

```java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping("/greet")
    public String greet(@RequestParam(name = "name", defaultValue = "Java 21") String name) {
        return service.greet(name);
    }
}
```

**File `src/main/resources/application.yml`** uses the content from section 5.3.

Mechanism explanation: `@SpringBootApplication` scans package `com.example.demo`; `@Service` registers `GreetingService`; `@RestController` registers `GreetingController`; the container sees the `GreetingController(GreetingService)` constructor and supplies the managed service. `@GetMapping` routes GET `/greet`; `@RequestParam` reads the query parameter `name`, defaulting to `Java 21` if omitted. The String is returned directly as the response body. There is no need to instantiate the controller or service with `new` inside `main()`.

Run in the `demo` directory:

```bash
mvn test
mvn spring-boot:run
```

While the application is running, open another terminal:

```bash
curl -s "http://localhost:8080/greet?name=Lan"
```

HTTP response body:

```text
Hello, Lan!
```

If you call `http://localhost:8080/greet` without passing `name`, the returned body is `Hello, Java 21!`. Do not treat the entire startup console log as fixed output, because startup duration, PID, and log lines vary.

Package and run the JAR:

```bash
mvn package
java -jar target/demo-0.0.1-SNAPSHOT.jar
```

If port `8080` is already in use, stop the existing process or change `server.port`. The `mvn test` command above will run the test once you add the test file below.

**File `src/test/java/com/example/demo/GreetingServiceTest.java`**

```java
package com.example.demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class GreetingServiceTest {
    @Test
    void greetsByName() {
        GreetingService service = new GreetingService();
        assertEquals("Hello, Lan!", service.greet("Lan"));
    }
}
```

This test is a **unit test** of the service logic: instantiating the service directly is valid because the container does not need to be tested here; it does not prove component scanning or HTTP mapping works. To test wiring/HTTP, you can learn `@SpringBootTest` or slice tests such as `@WebMvcTest` in dedicated testing lessons. Distinguish unit tests from integration tests instead of always booting the entire Spring context.

## 7. Recognizing and resolving common errors

| Symptom | Cause to check | Resolution |
| --- | --- | --- |
| `UnsupportedClassVersionError` | Java runtime is older than the compiled bytecode version | Check `java -version`, IDE/terminal JDK, and build target |
| `NoSuchBeanDefinitionException` or missing bean at startup | Class not scanned/imported, no bean of matching type, or configuration condition unmet | Check package, stereotypes, `@Bean`, dependencies, and conditions |
| `NoUniqueBeanDefinitionException` | Multiple beans of the same type available for injection | Disambiguate with `@Qualifier`/`@Primary` or adjust design |
| `BeanCreationException`/circular reference | Constructors or bean configs create a dependency cycle or fail during init | Read root cause, split responsibilities, break the dependency cycle |
| Port `8080` already in use | Another process holds the port | Stop the process or change the port |
| HTTP 404 when calling `/greet` | Wrong URL/port, controller not scanned, wrong mapping | Check endpoint, main class package, mapping logs |
| `javax.servlet.*` import error with Spring Boot 3 | Using older Java EE APIs/libraries incompatible with Jakarta | Use `jakarta.servlet.*` and Boot 3-compatible dependencies |
| Dependency conflict or `NoSuchMethodError` | Mixing library versions outside the BOM/parent | Inspect dependency tree, remove unnecessary overrides |
| Mutating a singleton field causes mixed results across requests | Unsynchronized shared mutable state | Keep services stateless, pass data via parameters or appropriate request scope |

When encountering errors, read the **first exception representing the root cause** (`Caused by`), check recent changes, dependency tree, active profiles, and environment variables. Do not rush to add random annotations or dependencies until you understand why the container is missing or duplicating a bean.

## 8. Self-check before moving to Application Runtime

Verify that you can answer and carry out these requirements:

1. Explain that Java 21 is the **language JDK/runtime**, Spring is the **framework**, and Boot is the **configuration/startup support layer**. Why does Spring Boot 3.3 not require Java 21, requiring at least Java 17 instead?
2. Write a record and a `switch` expression with pattern matching; explain the difference between shallowly immutable and deeply immutable records.
3. Explain why `List<String>` is not a `List<Object>`, when to use `Map`/`Set`, and why singleton services should avoid mutable per-request state.
4. Describe IoC, DI, and beans using the `GreetingController -> GreetingService` example. If two matching `GreetingService` implementations exist for the same type, how does the container decide?
5. Explain the purpose of `@SpringBootApplication`, `@Service`, `@RestController`, `@Bean`, `@GetMapping`, and constructor injection.
6. Predict what happens when `GreetingService` is moved outside the component-scanned package; know how to fix the package layout or register configuration appropriately.
7. Run `mvn test`, `mvn spring-boot:run`, call `/greet` with `curl`, and run the packaged JAR.
8. Try changing the port via a command-line argument, read the stack trace when the app fails to start, and know where to check dependency and Java versions.

**Effective learning order:** Core Java + collections/exceptions → Java 21 (records, switch, basic concurrency) → interfaces/composition → IoC and DI → Spring beans/context → Spring Boot starters, auto-configuration, externalized config → startup, request flow, and testing. Once completed, you can continue to deeper topics such as lifecycle events, configuration binding, Actuator, graceful shutdown, thread pools, and application observability.

## 9. Official references

- Java SE 21 Documentation: https://docs.oracle.com/en/java/javase/21/
- Spring Boot 3.3 — System Requirements: https://docs.spring.io/spring-boot/3.3/system-requirements.html
- Spring Boot 3.3 — Developing Your First Application: https://docs.spring.io/spring-boot/3.3/tutorial/first-application/
- Spring Framework Reference (IoC container): https://docs.spring.io/spring-framework/reference/core/beans.html
