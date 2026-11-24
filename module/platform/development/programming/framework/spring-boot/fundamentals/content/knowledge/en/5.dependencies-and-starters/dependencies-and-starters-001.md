# Which dependencies do starters bundle, and why are starters needed in Spring Boot?

When creating a Spring Boot project from Spring Initializr, you typically only select a few items such as **Spring Web**, **Spring Data JPA**, **Validation**, or **Spring Security**. After generating the project, `pom.xml` or `build.gradle` only contains a handful of dependencies named `spring-boot-starter-*`. Why does adding a single dependency allow the application to use many different libraries?

The answer lies in **starters** and **transitive dependencies**. A starter is a curated set of dependencies selected by Spring Boot for a common use case. It helps developers get started with a compatible group of libraries instead of searching for and assembling each library manually.

This lesson focuses on three topics: **which dependencies a starter actually brings in**, **why using starters is beneficial**, and **how to inspect or adjust those dependencies in your first project**.

## 1. First, what is a dependency?

In Java, an application often needs functionality from external libraries, such as handling HTTP, converting JSON, connecting to a database, or writing unit tests. Those libraries are the application's **dependencies**.

With Maven, you can declare a dependency in `pom.xml`:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
```

With Gradle Groovy DSL, the equivalent declaration in `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

In Gradle Kotlin DSL (`build.gradle.kts`):

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
}
```

The snippets above assume the project is already configured with Spring Boot dependency version management, such as using the parent/BOM in Maven or importing the BOM in Gradle. How Spring Boot determines versions is explained in Section 4.

The build tool reads the declaration, locates the artifact, and downloads the required libraries from a repository (such as Maven Central) or the local cache. The downloaded libraries are placed on the **classpath** at the appropriate phases, such as compile, runtime, or test.

### 1.1. Direct dependencies and transitive dependencies

- **Direct dependency**: a dependency you declare directly in the build file. For example, `spring-boot-starter-web`.
- **Transitive dependency**: a dependency required by another dependency; the build tool resolves it automatically. For example, the Web starter can bring in Spring MVC modules and a JSON processing library.

A simplified model:

```text
Your application
    └── spring-boot-starter-web                 ← direct dependency
         ├── Spring Web/MVC modules             ← transitive dependencies
         ├── JSON processing library            ← transitive dependencies
         ├── embedded web server                ← transitive dependencies
         └── core Spring Boot modules           ← transitive dependencies
```

This is a **conceptual diagram**: specific artifacts, depth, and versions vary across Spring Boot lines. To know exactly what the current project has downloaded, you need to inspect the dependency tree from Maven or Gradle.

## 2. What is a starter in Spring Boot?

A **Spring Boot starter** is a packaged and named dependency representing **a common development need**. For example:

- Want to build a REST API: use the starter for Spring Web/MVC.
- Want to persist data via JPA: use the Data JPA starter.
- Want authentication and authorization: use the Security starter.
- Want to test Spring Boot: use the Test starter.

A starter is usually primarily a **dependency-declaring artifact**, rather than a self-contained library holding every feature. When you declare a starter, the build system resolves the dependencies listed by the starter. Spring Boot can then rely on the libraries present on the classpath to activate the appropriate **auto-configuration**.

Distinguishing three layers:

```text
       build.gradle / pom.xml
                 │
                 ▼
     Starter (dependency group)
                 │
                 ▼
   Libraries present on the classpath
                 │
                 ▼
  Spring Boot evaluates auto-configuration conditions
                 │
                 ▼
  Beans/configuration are created if conditions are met
```

For example, adding the Web starter provides the components needed to handle HTTP in a Spring Boot web application. However, **a starter does not automatically turn any Java class into an endpoint**: you still have to declare controllers and mappings, and the application must be started properly.

## 3. Which libraries do common starters bundle?

The artifact names and dependency lists below describe common functional groups. Exact dependency structures may vary by Spring Boot version; in particular, newer versions may split, rename, or reorganize starters.

| Common starter | Purpose | Groups of components typically pulled in |
| --- | --- | --- |
| `spring-boot-starter` | Spring Boot foundation | Spring Core/Context, Spring Boot, auto-configuration, default logging depending on version |
| `spring-boot-starter-web` | Servlet-based HTTP/REST applications in common Spring Boot lines | Spring Web, Spring MVC, JSON, embedded servlet server such as Tomcat, Boot foundation |
| `spring-boot-starter-webflux` | Reactive web | Spring WebFlux, Project Reactor, default reactive HTTP server depending on configuration/version |
| `spring-boot-starter-data-jpa` | Relational data access via JPA | Spring Data JPA, Spring ORM, Hibernate, and JDBC/transaction foundation |
| `spring-boot-starter-jdbc` | SQL operations via JDBC | Spring JDBC, transactions, common connection pool |
| `spring-boot-starter-validation` | Declarative data validation with Jakarta Bean Validation | Jakarta Validation API and an implementation such as Hibernate Validator |
| `spring-boot-starter-security` | Authentication, authorization, and Spring Security integrations | Spring Security Core/Config/Web and related components |
| `spring-boot-starter-actuator` | Monitoring, health checks, and application management | Spring Boot Actuator and endpoint/observability components |
| `spring-boot-starter-test` | Testing | Spring Boot Test, JUnit Jupiter, Spring Test, AssertJ, Mockito, and other supporting libraries depending on version |

**Important note on versions:** the table uses familiar Spring Boot starter names, especially in Spring Boot 3.x projects. Other Spring Boot lines may use more specific starter names (for example, by MVC technology) or reorganize dependencies. Use the build file generated for **the exact version you are using** and the dependency tree output as your source of confirmation.

### 3.1. Web Starter: why is a single declaration enough to build a REST API?

Consider a servlet-style Spring Boot application. To respond to an HTTP request, multiple pieces are needed:

1. **Spring Web and Spring MVC**: receive requests, route URLs, invoke controller methods, and create responses.
2. **Content converters**: for example, converting Java objects into JSON via the configured JSON library.
3. **Embedded web server**: such as Tomcat in many default configurations, accepting HTTP connections without needing to deploy a WAR to a standalone server.
4. **Spring Boot and foundational configuration**: creating the application context, registering beans, and setting sensible defaults.

If you chose each dependency manually, you would have to understand each module, their compatibility relationships, and how to configure them. The Web starter bundles them into a suitable choice for most basic REST APIs.

Example controller:

```java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    @GetMapping("/greeting")
    public Greeting greeting() {
        return new Greeting("Hello", 200);
    }

    public record Greeting(String message, int code) {}
}
```

With a Spring Boot application that has an appropriate web starter, the controller class inside the component scan scope, and the application running on the default port, accessing:

```text
GET http://localhost:8080/greeting
```

Example JSON response:

```json
{
  "message": "Hello",
  "code": 200
}
```

`@RestController` and `@GetMapping` provide metadata for Spring MVC. HTTP message converters handle response representation; when an appropriate JSON converter is used, the object is serialized into JSON. Across different versions/configurations, the default JSON library and how dependencies are organized may differ.

### 3.2. Data JPA Starter: bundling ORM and Spring Data integration

To access a relational database with JPA, an application typically needs:

- Jakarta Persistence API (the JPA standard).
- A popular JPA provider/ORM such as Hibernate.
- Spring Data JPA to declare repositories and reduce boilerplate query code.
- Spring ORM and transaction management capabilities.
- Appropriate JDBC components and a connection pool.

The Data JPA starter brings these foundational components together so they work seamlessly with Spring Boot. For example:

```java
package com.example.demo;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Product() {} // JPA uses a no-arg constructor

    public Product(String name) {
        this.name = name;
    }

    public Long getId() { return id; }
    public String getName() { return name; }
}
```

```java
package com.example.demo;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository extends JpaRepository<Product, Long> {
}
```

Spring Data JPA can generate repository implementations and integrate with `EntityManager`. However, **the Data JPA starter does not replace the JDBC driver for your chosen database**. If you use PostgreSQL, you need to add the corresponding driver and configure the datasource:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'org.postgresql:postgresql'
}
```

Example `application.properties` for a learning environment:

```properties
spring.datasource.url=jdbc:postgresql://localhost:5432/demo
spring.datasource.username=demo_user
spring.datasource.password=${DB_PASSWORD}
```

To run, the database must actually exist and be accessible; you need to provide the `DB_PASSWORD` environment variable and configure an appropriate schema/migration strategy. Having the starter does not mean the application automatically creates a PostgreSQL server or knows the connection details.

### 3.3. Security Starter: adding libraries can also change default behavior

In a web project, adding `spring-boot-starter-security` typically brings the required Spring Security components onto the classpath. When default auto-configuration applies and no application-defined security configuration exists yet, Spring Boot can set up HTTP protection with default behavior.

This explains why an endpoint that was previously freely accessible may, after adding the Security starter, require authentication or return `401 Unauthorized`/a login page, depending on the request type and configuration.

**Takeaway:** starters prepare dependencies, while features are activated depending on auto-configuration conditions and application configuration. When adding a starter, always check if any runtime behavior changes.

### 3.4. Test Starter: a toolkit for the test scope

Spring Boot testing typically uses multiple libraries: a test runner framework (JUnit Jupiter), assertions (AssertJ), mocking (Mockito), Spring Test, and Spring Boot Test utilities. The Test starter saves you from picking each library individually.

In Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

In Gradle:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

**The `test` / `testImplementation` scope matters:** libraries used only for writing and running tests do not need to be on the production application's runtime classpath. Managing scopes properly reduces artifact size and avoids carrying unnecessary libraries.

## 4. How do starter, dependency management, and auto-configuration differ?

These three concepts often appear together and are easily mistaken for one.

| Component | Question answered | Role |
| --- | --- | --- |
| **Starter** | *Which libraries are needed for this feature?* | Groups related dependencies into a single declaration point |
| **Dependency management / BOM** | *Which version should be used?* | Manages a set of library versions compatible with a Spring Boot release line |
| **Auto-configuration** | *Once the libraries and conditions are in place, what should Spring configure?* | Creates/configures beans based on classpath, properties, existing beans, and other conditions |

They complement each other; they should not be conflated.

### 4.1. BOM solves versions, starter solves dependency grouping

Suppose an application needs Spring MVC, Jackson, Hibernate, and related libraries. If you specify individual versions for every artifact, upgrading could create conflicts:

```text
spring-webmvc       version A
spring-core         version B
jackson-*           version C
hibernate-core      version D
...
```

A **BOM** (*Bill of Materials*) is a set of version management rules tested to work together. With Maven, a project using `spring-boot-starter-parent` can inherit Spring Boot's dependency management:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
</parent>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
```

`3.3.5` in the example snippet merely illustrates how to declare the Spring Boot version in the parent; use the actual supported version chosen by your project. When dependencies are managed by the parent/BOM, you usually do not need to specify `<version>` on each starter.

If you do not use the Spring Boot parent, Maven can import the BOM in `dependencyManagement`:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.5</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Gradle can also use the BOM via `platform(...)` or a compatible dependency management mechanism:

```groovy
dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

The BOM snippets are **alternative setup approaches in illustrative projects**, not snippets that must all be copied at once into every project. When initializing from Spring Initializr, you usually just keep the generated build configuration and upgrade versions according to your project's plan.

Not **every** external library is included in the BOM; an unmanaged dependency still requires an explicit version or an appropriate version management source.

### 4.2. Auto-configuration works based on conditions

Spring Boot can automatically register configurations when it detects certain classes on the classpath and other conditions are satisfied. Several key condition types include:

```java
@ConditionalOnClass(SomeLibrary.class)
@ConditionalOnMissingBean(SomeService.class)
@ConditionalOnProperty(name = "feature.enabled", havingValue = "true")
```

A conceptual example: if JDBC libraries and an appropriate datasource library are present, and connection configuration is provided, Spring Boot can configure a `DataSource` and related beans. If the application defines a replacement bean itself, an auto-configuration can back off thanks to `@ConditionalOnMissingBean`.

Therefore, **simply adding a starter does not mean every bean is created**. Some auto-configurations require additional dependencies, properties, a servlet/reactive environment, or other beans. There are cases where you want to customize or disable a specific auto-configuration instead of removing the entire starter.

To see why an auto-configuration was selected or skipped, you can run the Spring Boot application with the condition evaluation report, for example:

```text
--debug
```

In an application with appropriate startup logging enabled, Spring Boot will print the **Conditions Evaluation Report** to assist with diagnostics. Do not confuse Spring Boot's `--debug` with running the JVM through an IDE debugger.

## 5. Why are starters needed?

### 5.1. Reducing repetitive declaration and configuration work

Instead of having to remember the names and relationships of many dependencies, you only need to declare the intent: Web, Data JPA, Security, or Test. This is especially helpful for newcomers learning Spring Boot, as they can focus on controllers, services, and business logic.

### 5.2. Reducing the risk of version incompatibility

Starters together with Spring Boot's dependency management mechanism help select a set of dependencies commonly tested together. When changing the Spring Boot version, many foundational library versions can be managed centrally.

However, this is not a guarantee that **every** additional dependency, custom override, or plugin is compatible. If you manually force a library to a different version, you can still cause classpath errors.

### 5.3. Leveraging convention-based default configuration

When a common set of libraries is present, auto-configuration can create many suitable default beans. For instance, the web starter can help configure the embedded server, MVC infrastructure, and JSON converters so you can start writing endpoints faster.

You can still adjust configurations when needed: change the port, add interceptors, declare a `SecurityFilterChain`, use a custom datasource, or replace default components.

### 5.4. Making projects easier to read and share with the team

Looking at the build file:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    runtimeOnly 'org.postgresql:postgresql'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

A teammate can immediately see that the project builds a web application, uses JPA and PostgreSQL, validates data with Bean Validation, and includes test support. This list communicates **architectural intent** more clearly than dozens of scattered library declarations.

### 5.5. Convenient for CI environments and reproducible builds

The Maven/Gradle wrapper combined with starter and BOM configurations allows other environments to resolve dependencies using the same declarations in the repository. For builds requiring strict reproducibility, you still need repository management, artifact management, lockfiles/verification, or corresponding version policies; starters alone do not replace those elements.

## 6. Inspecting the exact dependencies pulled in by a starter

**Do not guess from the starter name when you need to know the actual dependencies.** Build tools can display the resolved dependency tree.

### 6.1. Maven: `dependency:tree`

In the directory containing `pom.xml`, use the Maven wrapper:

**macOS/Linux**

```bash
./mvnw dependency:tree
```

**Windows PowerShell**

```powershell
.\mvnw.cmd dependency:tree
```

The output typically renders as a tree, with child lines under directly declared dependencies. A simplified example:

```text
com.example:demo:jar:0.0.1-SNAPSHOT
\- org.springframework.boot:spring-boot-starter-web:jar:...:compile
   +- org.springframework.boot:spring-boot-starter:jar:...:compile
   +- org.springframework:spring-web:jar:...:compile
   \- org.springframework:spring-webmvc:jar:...:compile
```

This diagram only illustrates how to read a dependency tree; components such as JSON, embedded server, Spring Core, and deeper dependencies have been omitted. Maven will display the actual resolved versions and scopes.

To find a specific dependency, add a filter using Maven Dependency Plugin syntax:

```bash
./mvnw dependency:tree -Dincludes=org.springframework:spring-webmvc
```

If running PowerShell and passing `-D...` properties causes argument parsing issues, wrap the entire argument in quotes:

```powershell
.\mvnw.cmd dependency:tree "-Dincludes=org.springframework:spring-webmvc"
```

### 6.2. Gradle: `dependencies` and `dependencyInsight`

In the root directory of the Gradle project:

**macOS/Linux**

```bash
./gradlew dependencies --configuration runtimeClasspath
```

**Windows PowerShell**

```powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
```

`runtimeClasspath` represents the dependencies resolved for running the main Java source set. To see why a library is present, such as Spring MVC:

```bash
./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath
```

In Gradle, different dependency configurations serve different purposes:

| Configuration | Typical meaning |
| --- | --- |
| `implementation` | Declares libraries needed for application code |
| `runtimeOnly` | Libraries needed only at runtime, such as a JDBC driver |
| `compileOnly` | Needed at compile time but not placed on the runtime classpath from this declaration |
| `testImplementation` | Libraries for writing and compiling tests |
| `testRuntimeOnly` | Libraries needed only at test runtime |

The dependency tree shows not only names, but also transitive relationships, version selection behavior, and dependencies that were replaced/conflicted according to the build tool's resolution rules.

### 6.3. How to read a dependency tree

Hypothetical example:

```text
demo
├── starter-web
│   ├── spring-webmvc
│   │   └── spring-web
│   └── embedded-server
└── starter-data-jpa
    ├── spring-data-jpa
    └── hibernate-core
```

Here `starter-web` and `starter-data-jpa` are directly declared by the project. `spring-webmvc`, `spring-data-jpa`, and `hibernate-core` are pulled in transitively. A library can appear via multiple dependency paths; Maven or Gradle resolves and selects a version according to the tool's rules.

When encountering `NoClassDefFoundError`, `NoSuchMethodError`, or conflicts between libraries, inspecting the dependency tree is usually much more helpful than adding a random dependency.

## 7. When should you not rely solely on default starters?

Starters are convenient, but you are not forced to use every default choice. Several cases require explicitly adding or replacing dependencies.

### 7.1. Adding a specific JDBC driver

As in the JPA example, the starter prepares ORM and Spring Data, but a specific database may require its own driver. PostgreSQL, MySQL, MariaDB, or Oracle have different drivers and connection configurations. Choose the driver matching your database and manage a compatible version.

### 7.2. Replacing the default web server

In many servlet projects using `spring-boot-starter-web`, Tomcat is pulled in by default. If you need Jetty in a Spring Boot version that supports it, you can exclude Tomcat and add the corresponding Jetty starter.

Maven example for a common starter organization:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-tomcat</artifactId>
        </exclusion>
    </exclusions>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jetty</artifactId>
</dependency>
```

Server choices and starter coordinates must be checked against **your actual Spring Boot version**; this pattern does not apply verbatim to every release line. After excluding a dependency, re-verify the dependency tree and startup behavior.

With Gradle, the idea is similar:

```groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }
    implementation 'org.springframework.boot:spring-boot-starter-jetty'
}
```

Excluding a dependency is an intentional tool; if you accidentally exclude a required library, the application may fail to compile or start.

### 7.3. Using modules directly when the entire starter is unnecessary

There are cases where you only need part of a capability, such as a specific Spring module in a shared library or a command-line tool that does not run a web server. In that case, declaring the dependency directly may be more appropriate:

```groovy
dependencies {
    implementation 'org.springframework:spring-context'
}
```

However, if it is a full Spring Boot application, using a starter for common needs is usually simpler. **The goal is to choose just the dependencies you need**, rather than adding as many starters as possible.

### 7.4. Third-party starters

Not all starters are published by the Spring Boot team. Third-party libraries may also provide Spring Boot integration starters, commonly following a naming convention like `library-name-spring-boot-starter`.

For instance, a service integration starter might pull in a client SDK and the vendor's auto-configuration modules. Therefore, you should check:

- The publisher, version, and maintenance status of the starter.
- The list of transitive dependencies, including runtime libraries.
- Required configuration conditions, environment variables, and security settings.
- Compatibility with the Spring Boot version in use.

Do not infer the quality or compatibility of a starter merely from the `starter` suffix in its name.

## 8. Common misconceptions

| Misconception | Accurate explanation |
| --- | --- |
| “A starter is a library containing all of Spring Boot.” | A starter mainly bundles dependencies for a specific need; functionality lives in the libraries it pulls in. |
| “Simply adding a starter makes the feature work immediately.” | You may still need classes, annotations, configuration, connections, and matching auto-configuration conditions. |
| “Starters decide every dependency version on their own.” | The BOM/dependency management determines managed versions; starters determine the dependency group. |
| “To use PostgreSQL, you only need Data JPA.” | You usually also need the PostgreSQL JDBC driver, a database, and datasource configuration. |
| “The Web starter always contains the exact same JARs.” | Components, modules, and starter names may vary by version and resolution. |
| “Add all starters for convenience.” | Increases dependencies, can increase footprint, and can trigger unwanted behavior such as security configuration. |
| “Having a dependency in `pom.xml` means it is always in the production JAR.” | It depends on scope, packaging, plugins, and the artifact build process. |
| “A starter and a wrapper are the same thing.” | Starters bundle libraries; the Gradle/Maven wrapper ensures running the right build tool version. |

### 8.1. Should you add both Spring Web and WebFlux?

The two stacks serve different development models: Spring MVC typically uses servlets and a blocking programming style; WebFlux supports reactive programming. Both can coexist on an application's classpath in certain scenarios, but adding both starters just to “have enough libraries” easily causes confusion about the application type, server, and request handling. You should decide on the web model you want to use and choose dependencies deliberately.

### 8.2. Why do errors still occur after adding a starter?

It could be due to one of the following reasons:

1. The dependency was not declared in the appropriate scope/configuration.
2. Maven/Gradle has not synced, or the repository failed to download the artifact.
3. The JDK/build tool is incompatible with the Spring Boot version.
4. External components are missing, such as a database, driver, broker, or connection details.
5. Manual version overrides caused conflicts.
6. Auto-configuration conditions are not satisfied or have been excluded.
7. Components are outside the package scan range, missing annotations, or missing required beans.

To find the cause, read the startup logs, inspect the dependency tree, and check the corresponding configuration instead of blaming the starter by default.

## 9. Hands-on practice on your first Spring Boot project

### Exercise 1 — Observe the pulled-in dependencies

Create a project from Spring Initializr selecting only **Spring Web** and **Spring Boot Test** with the generated configuration. Open `pom.xml` or `build.gradle` to identify which are direct dependencies.

Run the command to display the dependency tree:

```bash
# Gradle
./gradlew dependencies --configuration runtimeClasspath

# Maven
./mvnw dependency:tree
```

Only run the command matching your chosen build tool. On Windows, use `gradlew.bat` or `mvnw.cmd` instead of the Unix scripts. Find the HTTP, MVC, JSON, and web server modules in the tree; record their **actual names** rather than relying solely on the diagrams in this lesson.

### Exercise 2 — Add Validation

Add the Validation starter corresponding to your Spring Boot version and create a request DTO:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateProductRequest(
    @NotBlank String name,
    @Size(min = 3, max = 20) String sku
) {}
```

When `@Valid` is placed on the `@RequestBody` parameter and appropriate validation infrastructure is present, Spring MVC can validate data against the constraints:

```java
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProductController {
    @PostMapping("/products")
    public String create(@Valid @RequestBody CreateProductRequest request) {
        return "Created: " + request.name();
    }
}
```

Try sending JSON with `"name": ""` to observe the response when validation fails. Then inspect the dependency tree to confirm which Bean Validation implementation library the Validation starter pulls in for your current version.

### Exercise 3 — Observe the impact of Security

In a separate test web project, access the `/greeting` endpoint **without** the Security starter. Then add the Security starter, restart, and try accessing the URL again. Compare the HTTP status and startup logs.

Explain: what comes from **the dependency being present on the classpath**, and what comes from **auto-configuration**? After experimenting, you can configure security appropriately for your application's needs instead of relying on default behavior.

### Exercise 4 — Choose starters based on requirements

Choose appropriate dependencies for the following requirements and explain whether additional configuration is needed:

| Requirement | Suggested selection |
| --- | --- |
| REST API receiving/returning JSON via Spring MVC | Web/MVC starter appropriate for the version |
| Save `Product` to PostgreSQL using a JPA repository | Data JPA + PostgreSQL driver + datasource |
| Validate `@NotBlank` in the request body | Validation starter + `@Valid` and constraints |
| Protect endpoints requiring login | Security starter + authentication/authorization configuration |
| Write unit tests with JUnit and Mockito | Test starter in test scope |
| Check operational health | Actuator starter + exposure/security configuration for required endpoints |

## 10. Key takeaways

**A starter is a convenient selection for a group of dependencies**, while **transitive dependencies** explain why declaring one starter downloads multiple libraries. **Dependency management/BOM** helps align versions, while **auto-configuration** uses runtime conditions to configure the application based on the libraries and configuration present.

When encountering a new starter, ask three questions:

1. **What need does it address?** For example, HTTP, JPA, Security, or Test.
2. **Which libraries does it pull in for the current project version?** Check `dependency:tree` or `dependencies`.
3. **What additional configuration or external services does the application still need to run?** For example, datasource, JDBC driver, controllers, or security policies.

Understanding these three points helps you choose the right starters, read build files with greater confidence, and resolve dependency issues methodically as you build future Spring Boot applications.
