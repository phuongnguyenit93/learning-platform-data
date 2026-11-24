# Impact of Dependencies and Application Type Selection on Web Configuration Branches

## 1. Goal and Core Question

Spring Boot can automatically select a web configuration branch based on the libraries present on the runtime classpath and the application type used by `SpringApplication`. Thus, simply adding or removing a starter can move an application from the **Servlet/MVC** branch to **Reactive/WebFlux**, or to a non-web context. However, classpath and application type selection are two distinct factors: a class may be present, yet the corresponding configuration branch still will not be applied if the application type has been explicitly set.

This lesson focuses on Spring Boot **3.3.13**, Spring Framework 6.1, and Java 17+. After this lesson, you should understand:

1. Which components `spring-boot-starter-web` and `spring-boot-starter-webflux` bring into the dependency graph.
2. How Spring Boot deduces `WebApplicationType` when MVC is present, only WebFlux is present, both are present, or neither web stack is present.
3. How to explicitly choose `SERVLET`, `REACTIVE`, or `NONE` via property and Java API.
4. How `@ConditionalOnClass` coordinates with `@ConditionalOnWebApplication` to select the right auto-configuration branch.
5. Why server dependencies (Tomcat, Jetty, Undertow, Reactor Netty) are a separate decision from application type.
6. How to test each branch without accidentally running the wrong context type.

**Key takeaway:** dependencies determine which classes can be discovered; `WebApplicationType` determines which web environment type Boot selects; auto-configuration conditions decide which configurations are actually applied.

## 2. Three Concepts Not to Equate

### 2.1. Dependencies and Runtime Classpath

A dependency is an artifact resolved by Maven/Gradle and placed on the compile/runtime classpath according to its scope/configuration. For example:

- `spring-webmvc` provides Spring MVC and `DispatcherServlet`.
- `spring-webflux` provides Spring WebFlux and `DispatcherHandler`.
- `spring-boot-starter-web` pulls in components for a Servlet/MVC application, including the default Tomcat starter.
- `spring-boot-starter-webflux` pulls in components for WebFlux, including Reactor Netty by default.

When adding a starter, many transitive dependencies may appear. When removing a starter, the corresponding classes disappear only if no other dependency pulls that artifact in. Therefore, inspect the actual dependency graph instead of looking at only one line in `pom.xml`.

### 2.2. Application Type: `WebApplicationType`

Spring Boot 3.3 has three values:

| Value | Meaning |
| --- | --- |
| `SERVLET` | Servlet-based web application; Boot creates a servlet web application context and may start an embedded servlet server |
| `REACTIVE` | Reactive web application; Boot creates a reactive web application context and may start an embedded reactive server |
| `NONE` | Application does not run as a web application and does not start an embedded web server |

`WebApplicationType` is not a server name. `SERVLET` does not necessarily mean Tomcat must be used; `REACTIVE` also does not necessarily mean Reactor Netty must be used. The server can be replaced with a supported implementation.

### 2.3. Auto-Configuration Branch

An auto-configuration may simultaneously require:

- Required library classes exist (`@ConditionalOnClass`).
- ApplicationContext is Servlet or Reactive (`@ConditionalOnWebApplication`).
- A matching bean already exists or does not yet exist (`@ConditionalOnBean` / `@ConditionalOnMissingBean`).
- Properties satisfy conditions (`@ConditionalOnProperty`).

Therefore, "the dependency is present" is not enough to conclude "the auto-configuration ran." Another condition may still not match.

## 3. Spring Boot Deduces WebApplicationType from the Classpath

According to Spring Boot 3.3 documentation, when `SpringApplication` automatically chooses the context type, the general rule is:

1. If Spring MVC is present, Boot chooses **Servlet**.
2. If Spring MVC is absent and Spring WebFlux is present, Boot chooses **Reactive**.
3. If neither is present, Boot chooses **Non-web**.

If both MVC and WebFlux are present, **MVC takes precedence by default**. This case often arises when an MVC application adds the WebFlux starter to use `WebClient`. Having `spring-webflux` on the classpath does not automatically switch the entire application to reactive.

### 3.1. Decision Table by Dependency

| Components on runtime classpath | Default deduced type | Context branch typically selected |
| --- | --- | --- |
| Only Spring MVC / Servlet stack | `SERVLET` | Servlet web context |
| Only Spring WebFlux stack | `REACTIVE` | Reactive web context |
| Both MVC and WebFlux | **`SERVLET`** | MVC/Servlet; WebFlux can still provide APIs such as WebClient |
| Neither MVC nor WebFlux | `NONE` | Plain Spring context, no web server |

The table above describes the default deduction of `SpringApplication`. Applications can override the application type; additionally, other conditions and custom configurations still affect the final beans.

### 3.2. Corresponding Contexts

When using Spring Boot 3.3's default factory:

- `SERVLET` → `AnnotationConfigServletWebServerApplicationContext`.
- `REACTIVE` → `AnnotationConfigReactiveWebServerApplicationContext`.
- `NONE` → `AnnotationConfigApplicationContext`.

These are the corresponding default context types. Applications can customize `ApplicationContextFactory` for special needs, so do not treat the default context class name as the only way to create an application.

### 3.3. Easy-to-Confuse Example: Using WebClient in an MVC Application

A project may use Spring MVC controllers while wanting to call another service with `WebClient`. `WebClient` belongs to Spring WebFlux. If you add `spring-boot-starter-webflux` to a project that already has `spring-boot-starter-web`, Boot still selects MVC by default because both stacks are present and MVC takes precedence.

That allows the application to use `WebClient` without necessarily switching controllers, the server, and the entire auto-configuration branch to reactive. Distinguish **using a reactive API as an HTTP client** from **running the server under the reactive web application type**.

## 4. Server Dependency and Application Type Are Two Separate Decisions

### 4.1. Default Starters Bring an Embedded Server

In Spring Boot 3.3:

- `spring-boot-starter-web` includes `spring-boot-starter-tomcat` by default for the Servlet stack.
- `spring-boot-starter-webflux` includes `spring-boot-starter-reactor-netty` by default for the reactive stack.

Boot also supports swapping the embedded server:

| Stack | Default server from starter | Other supported options |
| --- | --- | --- |
| Servlet/MVC | Tomcat | Jetty, Undertow |
| Reactive/WebFlux | Reactor Netty | Tomcat, Jetty, Undertow |

Therefore, choosing `SERVLET` is not choosing Tomcat; choosing `REACTIVE` is not choosing Reactor Netty. Application type determines the web branch; the server dependency provides the corresponding server implementation.

### 4.2. Replacing Tomcat with Jetty in the Servlet Stack

Maven example:

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

The application remains Servlet/MVC; the server dependency was changed. Ensure only the intended server implementation remains in the dependency graph and re-check the runtime classpath.

### 4.3. Replacing Reactor Netty in the Reactive Stack

Maven example:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-reactor-netty</artifactId>
        </exclusion>
    </exclusions>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-tomcat</artifactId>
</dependency>
```

This illustrates swapping the server in the reactive stack, not turning the application into Servlet/MVC. WebFlux can run on servers supported by Spring Boot, including certain Servlet containers.

**Special note on WebClient:** `spring-boot-starter-reactor-netty` also provides the Reactor Netty needed for `WebClient` in some configurations. If you change the server while the application still needs `WebClient` with Reactor Netty, you may still need to keep the appropriate Netty dependency. Do not remove dependencies solely to change the embedded server.

## 5. Explicitly Selecting the Application Type

When you need to override classpath deduction, Spring Boot supports two ways.

### 5.1. Via Property

In `application.properties`:

```properties
spring.main.web-application-type=reactive
```

Valid values corresponding to the enum are `servlet`, `reactive`, and `none`. YAML example:

```yaml
spring:
  main:
    web-application-type: reactive
```

Some scenarios:

- Want to run WebFlux even when both MVC and WebFlux are present → `reactive`.
- Want to run Servlet/MVC → `servlet`.
- Want a non-web context without starting a server → `none`.

### 5.2. Via SpringApplication API

```java
SpringApplication application =
    new SpringApplication(MyApplication.class);

application.setWebApplicationType(WebApplicationType.REACTIVE);
application.run(args);
```

This is the explicit Java approach, suitable when startup logic needs to decide the application type based on the environment or an application-controlled parameter.

You can read the deduced value before running:

```java
SpringApplication application =
    new SpringApplication(MyApplication.class);

System.out.println(application.getWebApplicationType());
```

`getWebApplicationType()` returns the current application type that `SpringApplication` will use; if not explicitly set, the value is deduced from the classpath. Both `setWebApplicationType` and `getWebApplicationType` exist in Spring Boot 3.3.13.

### 5.3. `NONE` Differs from Disabling the HTTP Port

These two configurations are not equivalent:

```properties
spring.main.web-application-type=none
```

selects a non-web context. Meanwhile:

```properties
server.port=-1
```

can still create a `WebApplicationContext` while not opening an HTTP port like a normal application. Configuring `server.port=-1` is useful when you need a web context in tests without listening on a network port. If the goal is to have no web environment, choose `WebApplicationType.NONE` or the property `none`.

## 6. Choosing the Right Auto-Configuration Branch

### 6.1. Checking Classpath and Application Type Together

An auto-configuration meant only for MVC can be written as:

```java
@AutoConfiguration
@ConditionalOnClass(
    name = "org.springframework.web.servlet.DispatcherServlet"
)
@ConditionalOnWebApplication(
    type = ConditionalOnWebApplication.Type.SERVLET
)
public class ServletClientAutoConfiguration {
    // Beans only for Servlet/MVC ...
}
```

An auto-configuration meant for WebFlux:

```java
@AutoConfiguration
@ConditionalOnClass(
    name = "org.springframework.web.reactive.DispatcherHandler"
)
@ConditionalOnWebApplication(
    type = ConditionalOnWebApplication.Type.REACTIVE
)
public class ReactiveClientAutoConfiguration {
    // Beans only for WebFlux ...
}
```

These examples are illustrative snippets; concrete beans and dependencies must be defined in a real starter.

Meaning of the two conditions:

- `@ConditionalOnClass` asks whether the required class is on the classpath.
- `@ConditionalOnWebApplication` asks what web type the current context belongs to.

If both MVC and WebFlux are present and `WebApplicationType` is `SERVLET`, WebFlux classes may exist yet the reactive branch still fails `@ConditionalOnWebApplication(REACTIVE)`. Only when the application is forced to `REACTIVE` does the reactive branch have a chance to match; other classpath and bean conditions must still be satisfied.

### 6.2. `ANY` and `@ConditionalOnNotWebApplication`

`@ConditionalOnWebApplication` has the types:

- `ANY`: any type of web application.
- `SERVLET`: only Servlet-based web applications.
- `REACTIVE`: only Reactive-based web applications.

Example:

```java
@ConditionalOnWebApplication
class CommonWebConfiguration {
    // Shared across web applications.
}
```

The default `type` is `ANY`. For configuration meant only for non-web applications:

```java
@ConditionalOnNotWebApplication
class BatchOnlyConfiguration {
    // Configuration not meant for web applications.
}
```

Do not use `@ConditionalOnClass` alone to conclude whether the application is running MVC or WebFlux. The class may exist on the classpath in both cases.

### 6.3. Common Auto-Configuration Branches

In Spring Boot 3.3, there are separate configuration classes for each stack, such as:

| Branch | Example auto-configuration |
| --- | --- |
| Servlet/MVC | `org.springframework.boot.autoconfigure.web.servlet.WebMvcAutoConfiguration` |
| WebFlux | `org.springframework.boot.autoconfigure.web.reactive.WebFluxAutoConfiguration` |
| Servlet embedded server | `org.springframework.boot.autoconfigure.web.servlet.ServletWebServerFactoryAutoConfiguration` |
| Reactive embedded server | `org.springframework.boot.autoconfigure.web.reactive.ReactiveWebServerFactoryAutoConfiguration` |

These are class names to guide reading the right version's documentation/source; do not deduce that every web bean in the application comes only from one of these classes. Other auto-configurations may also contribute web support according to their own conditions.

## 7. Standalone Runnable Java 17+ Example: Inspecting Classpath and Application Type

The following example uses Spring Boot **3.3.13** and adds both `spring-boot-starter-web` and `spring-boot-starter-webflux`. The program only instantiates `SpringApplication` to inspect the deduced application type and the value after setting overrides; it **does not call `run()`**, so it neither opens a port nor starts an embedded server.

### 7.1. Directory Structure

```text
web-application-type-demo/
├── pom.xml
└── src/main/java/demo/WebTypeProbe.java
```

### 7.2. File `pom.xml`

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

    <groupId>demo</groupId>
    <artifactId>web-application-type-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <!-- Provides Spring MVC and default Tomcat -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <!-- Provides Spring WebFlux and default Reactor Netty -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

### 7.3. File `src/main/java/demo/WebTypeProbe.java`

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.util.ClassUtils;

@SpringBootApplication
public class WebTypeProbe {

    private static boolean classPresent(String className) {
        return ClassUtils.isPresent(
            className,
            WebTypeProbe.class.getClassLoader()
        );
    }

    private static void printType(
        String label,
        WebApplicationType explicitType
    ) {
        SpringApplication application =
            new SpringApplication(WebTypeProbe.class);

        if (explicitType != null) {
            application.setWebApplicationType(explicitType);
        }

        System.out.println(
            label + "=" + application.getWebApplicationType()
        );
    }

    public static void main(String[] args) {
        System.out.println(
            "mvcClass=" + classPresent(
                "org.springframework.web.servlet.DispatcherServlet"
            )
        );
        System.out.println(
            "webFluxClass=" + classPresent(
                "org.springframework.web.reactive.DispatcherHandler"
            )
        );

        // No type set: Boot deduces from classpath.
        printType("default", null);

        // Override the deduced result.
        printType("forcedServlet", WebApplicationType.SERVLET);
        printType("forcedReactive", WebApplicationType.REACTIVE);
        printType("forcedNone", WebApplicationType.NONE);
    }
}
```

### 7.4. Running the Program

Requirements: JDK 17+, Maven 3.6.3+, and permission to download dependencies. In the `web-application-type-demo` directory, run:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.WebTypeProbe
```

For Maven to run `exec:java`, add the `exec-maven-plugin` plugin under `build/plugins`:

```xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>exec-maven-plugin</artifactId>
    <version>3.3.0</version>
</plugin>
```

With both starters in the POM, the lines printed by the program itself are:

```text
mvcClass=true
webFluxClass=true
default=SERVLET
forcedServlet=SERVLET
forcedReactive=REACTIVE
forcedNone=NONE
```

Explanation:

1. `mvcClass=true` because the web starter brings Spring MVC/`DispatcherServlet` onto the runtime classpath.
2. `webFluxClass=true` because the WebFlux starter brings `DispatcherHandler` onto the runtime classpath.
3. `default=SERVLET` because when both stacks are present, Spring Boot prioritizes Spring MVC by default rules.
4. `forcedServlet=SERVLET` confirms Servlet can be explicitly selected.
5. `forcedReactive=REACTIVE` confirms WebFlux can be selected even when MVC is still present.
6. `forcedNone=NONE` confirms the application can be instructed not to run as a web application.

**Demo limitation:** the program tests `SpringApplication` deduction/overrides and class loadability. It does not refresh the context, does not start a server, and does not prove all MVC/WebFlux beans are created successfully. To verify auto-configuration and real endpoints, run the context/application and write dedicated tests.

### 7.5. Trying Other Dependency Graphs

Keep the Java file unchanged, modify the dependencies in the POM, and re-run:

| POM | `mvcClass` | `webFluxClass` | Expected `default` |
| --- | :---: | :---: | --- |
| Only `spring-boot-starter-web` | true | false | `SERVLET` |
| Only `spring-boot-starter-webflux` | false | true | `REACTIVE` |
| Both starters | true | true | `SERVLET` |
| Only `spring-boot-starter` | false | false | `NONE` |

This table assumes no other dependency on the runtime classpath pulls in Spring MVC or WebFlux. If another dependency brings in the corresponding class, the deduced result may differ. This is why you must inspect the dependency tree rather than looking only at direct starters.

## 8. Testing the Right Context Type and Configuration Branch

### 8.1. Testing MVC and WebFlux Applications

With `@SpringBootTest`, when both MVC and WebFlux are present, MVC is selected by default. If a test needs WebFlux, set the property:

```java
@SpringBootTest(
    properties = "spring.main.web-application-type=reactive"
)
class MyWebFluxTests {
    // Testing reactive application.
}
```

If you want to test MVC on the same classpath, you can use the default configuration or explicitly set `servlet`:

```java
@SpringBootTest(
    properties = "spring.main.web-application-type=servlet"
)
class MyMvcTests {
    // Testing servlet/MVC application.
}
```

Do not let a WebFlux test run with the default when both starters are on the test runtime classpath and then conclude that reactive auto-configuration is broken. First confirm the actual application type.

### 8.2. Choosing the Right Test Slice

- `@WebMvcTest` focuses on the Spring MVC layer.
- `@WebFluxTest` focuses on the Spring WebFlux layer.
- `@SpringBootTest` tests a broader application context; `webEnvironment` determines a mock environment or a real server.

With `@SpringBootTest`:

| `webEnvironment` | Meaning |
| --- | --- |
| `MOCK` (default) | Creates a web ApplicationContext and mock environment; does not start an embedded server |
| `RANDOM_PORT` | Starts a real server on a random port |
| `DEFINED_PORT` | Starts a real server on the configured or default port |
| `NONE` | Creates an ApplicationContext without a web environment |

`webEnvironment` is a test choice; `spring.main.web-application-type` is an application type choice. Do not treat these two properties as a single concept. When testing reactive on a classpath that also contains MVC, set the reactive type explicitly.

### 8.3. Testing Individual Auto-Configurations

The default `ApplicationContextRunner` is suited for non-web contexts. If an auto-configuration depends on the web application type, use the corresponding web runner such as `WebApplicationContextRunner` or `ReactiveWebApplicationContextRunner` as appropriate for your Boot version and test dependencies.

Additionally, inspect the condition report via `ConditionEvaluationReport` or run the application with `--debug` to see why a condition did not match. In tests, prefer assertions on beans and endpoint results over reading logs alone.

## 9. Diagnosing When the Application Runs the Wrong Branch

1. **Check the application type first:** log/read `SpringApplication.getWebApplicationType()` at a suitable startup point or check the actual context type.
2. **Check the classpath:** inspect `mvn dependency:tree` or Gradle `runtimeClasspath` to identify what brings in `spring-webmvc` or `spring-webflux`.
3. **Check the condition report:** use `--debug` or `ConditionEvaluationReport` to find unmatched class, web application, property, and bean conditions.
4. **Check overrides:** look for `spring.main.web-application-type` in config files, environment variables, command-line arguments, and `SpringApplication` customizations.
5. **Check server dependencies:** determine whether Tomcat/Jetty/Undertow/Reactor Netty resolved properly and were not mistakenly excluded.
6. **Check test type:** a non-web `ApplicationContextRunner` can cause `@ConditionalOnWebApplication` not to match; use the runner/context matching the stack.
7. **Check custom beans:** application-supplied beans can cause auto-configuration to back off; do not conclude solely from context type.
8. **Check server configuration:** port, SSL, and embedded container settings can cause startup failure after the application type was already selected correctly.

Dependency inspection commands:

```bash
mvn dependency:tree -Dincludes=org.springframework:spring-webmvc,org.springframework:spring-webflux
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-tomcat,org.springframework.boot:spring-boot-starter-reactor-netty
```

With Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-webmvc
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-webflux
```

Run these on the exact application module; in a multi-project Gradle build, a library module's dependency graph may differ from the runnable application module's.

## 10. Common Pitfalls and Fixes

| Misconception / Error | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| Adding the WebFlux starter automatically switches the app to Reactive | If both MVC and WebFlux are present, Boot prioritizes MVC | Set `spring.main.web-application-type=reactive` if a reactive server is truly wanted |
| Having `DispatcherHandler` means WebFlux is definitely running | The class can exist in an MVC app solely to use WebClient | Check `WebApplicationType` and `@ConditionalOnWebApplication` |
| Choosing `REACTIVE` forces using Reactor Netty | Application type and server implementation are two separate choices | Choose the server dependency separately per Boot's guide |
| Choosing `NONE` is the same as `server.port=-1` | `NONE` creates a non-web context; port -1 can still retain a web context | Pick the right one for your test/run goal |
| Checking only direct dependencies in the POM | Another starter may pull in MVC/WebFlux via transitive dependencies | Check `runtimeClasspath` or `dependency:tree` |
| Using `@ConditionalOnClass` to distinguish Servlet/Reactive | Class conditions only check class presence, not application type | Combine with `@ConditionalOnWebApplication(type=...)` |
| Using plain ApplicationContextRunner to test web branches | Non-web runner does not simulate Servlet/Reactive web contexts | Use a web runner or `@SpringBootTest` with the right property |
| Thinking switching Tomcat to Jetty switches to WebFlux | Both can be servers for the Servlet stack | Keep application type and swap server dependencies per stack |
| Thinking removing the server dependency removes all of Spring Web | Web API and embedded server are separate dependencies | Check classpath and context type; remove the exact needed artifact |
| Testing WebFlux without overriding when MVC is also present | Boot selects MVC by default | Set `spring.main.web-application-type=reactive` in the test |

## 11. Self-Check Exercises

**Question 1.** A POM has both `spring-boot-starter-web` and `spring-boot-starter-webflux`. Without overrides, what is the default application type?  
**Answer:** `SERVLET`. Spring MVC takes precedence when both are present.

**Question 2.** An MVC application needs to use `WebClient`. Is it mandatory to change the application type to `REACTIVE`?  
**Answer:** No. You can use the WebFlux client API in an MVC application; Boot still selects Servlet by default when both MVC and WebFlux are present.

**Question 3.** `@ConditionalOnClass(DispatcherHandler.class)` matches. Is that enough to prove the reactive branch is applied?  
**Answer:** No. The class can be present on an MVC classpath; you must also check `@ConditionalOnWebApplication(type = REACTIVE)` and other conditions.

**Question 4.** To force the application to run WebFlux even while MVC remains on the runtime classpath, what do you choose?  
**Answer:** `spring.main.web-application-type=reactive` or `SpringApplication.setWebApplicationType(WebApplicationType.REACTIVE)`.

**Question 5.** How do `spring.main.web-application-type=none` and `server.port=-1` differ?  
**Answer:** `none` selects a non-web context; port -1 can still create a web context without opening an HTTP port.

**Question 6.** Does choosing `SERVLET` mean the server must be Tomcat?  
**Answer:** No. Tomcat, Jetty, or Undertow can be used depending on matching dependencies.

**Question 7.** Why might a test for `@ConditionalOnWebApplication` fail to match when using `ApplicationContextRunner`?  
**Answer:** The plain runner creates a non-web context. Use the corresponding web runner or `@SpringBootTest` with the appropriate application type.

## 12. Takeaways and References

- **Dependencies** determine which classes/server implementations can appear on the runtime classpath.
- **`WebApplicationType`** determines whether Spring Boot chooses a non-web, Servlet, or Reactive context.
- Default: MVC present → Servlet; MVC absent but WebFlux present → Reactive; neither present → None.
- When both MVC and WebFlux are present, MVC takes precedence; to use reactive you must explicitly set `spring.main.web-application-type=reactive` or use the equivalent API.
- **Server implementation** (Tomcat, Jetty, Undertow, Reactor Netty) is a separate decision from application type.
- `@ConditionalOnClass` checks the classpath; `@ConditionalOnWebApplication` checks the web context type. Use both when a configuration branch depends on both the library and the environment.
- Tests must choose the right context type; condition logs aid diagnosis, while assertions verify behavior.

Official Spring Boot 3.3.13 documentation:

1. [SpringApplication — Web Environment and `setWebApplicationType`/`getWebApplicationType` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html).
2. [Testing Spring Boot Applications — Detecting Web Application Type](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html).
3. [Reactive Web Applications — WebFlux and MVC precedence](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html).
4. [Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html).
5. [Embedded Web Servers — swapping servers and disabling the web server](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html).
6. [`WebApplicationType` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/WebApplicationType.html).
7. [`@ConditionalOnWebApplication` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnWebApplication.html).
8. [Spring Boot 3.3.13 System Requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html).
