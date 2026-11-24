# Source Code, Configuration, Dependencies, and Environment Together Determine Application Behavior

A Spring Boot application does not behave solely according to the Java lines a developer writes. At runtime, Spring Boot combines **source code**, **libraries present on the classpath**, **effective configuration**, and **runtime environment conditions** to produce a concrete running application. Consequently, two runs from the exact same source code might listen on different ports, connect to different databases, return different responses, or even succeed on one startup and fail on another.

In the Spring Boot big picture, this is an essential lens for understanding why the framework can auto-configure so many components and why a bug can appear only on another machine or in a deployment environment.

## 1. What Does "Application Behavior" Encompass?

Behavior is not limited to a method's return value. For a Spring Boot web service, it can include:

- Whether the application starts at all, which port it opens, and which HTTP endpoints it registers.
- What status code, headers, response body, or error message a request receives.
- Which database, message broker, or external service the application connects to.
- Whether a feature is enabled or disabled; which beans are created and which bean is selected to handle work.
- What log level is recorded, where log files are written, and which time zone is used to interpret timestamps.
- How the application reacts when an environment variable is missing, DNS is unreachable, memory runs out, or connection limits are hit.

You can visualize it like this:

~~~text
Source code + resolved dependencies
                 |
                 v
         Build the application
                 |
                 v
  Runtime classpath + effective configuration
                 |
                 v
  Spring Boot initializes ApplicationContext
                 |
                 v
   Beans + auto-configuration + web server
                 |
                 v
    Behavior when handling requests/events
                 ^
                 |
     JVM, OS, network, DB,
     external resources and data
~~~

The diagram is a mental model, not a rigid sequence: source code can also read configuration directly; the environment can influence Spring during startup itself; requests and real data continue shaping outcomes afterward.

## 2. The Four Key Factors and Each Factor's Responsibility

| Factor | What Does It Determine? | Typical Examples | What Does Changing It Usually Require? |
|---|---|---|---|
| **Source code** | Business logic, endpoints, class structure, custom beans, and data processing | `@GetMapping("/hello")`, `@Service` classes, pricing rules | Edit code, compile, and produce a new build |
| **Dependencies** | Which APIs, frameworks, drivers, and integrations exist on the classpath; which auto-configuration conditions can be met | Spring MVC, Spring Data JPA, JDBC driver | Update dependency declarations, resolve versions, and rebuild |
| **Configuration** | Values used at runtime and switches enabling/disabling components | `server.port`, `spring.profiles.active`, database URL, feature flags | Can change values supplied at startup without editing Java; usually requires restart |
| **Environment** | Actual conditions inside which the process runs | JDK/JVM, environment variables, OS, CPU/RAM, network, DNS, file permissions, external services | Modify infrastructure, environment variables, resources, connectivity, or access rights |

These four factors are tightly connected. **Dependencies** make a capability possible; **configuration** provides the values and conditions to use that capability; **source code** determines how the application uses it; **environment** determines whether it can actually operate in reality.

For example, adding the PostgreSQL connector library does not create a database. Configuring a valid URL and credentials accomplishes nothing if the required driver is missing. Even when both are right, the application still cannot connect if the database server is down or the network blocks traffic.

## 3. What Happens When a Spring Boot Application Starts?

In a plain Java application, the entry point is the `main` method. In Spring Boot, the entry point normally calls `SpringApplication.run(...)` inside a class annotated with `@SpringBootApplication`.

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

`@SpringBootApplication` combines key capabilities: declaring Spring configuration, component scanning from the appropriate package, and enabling auto-configuration. At runtime, Spring Boot orchestrates a series of related steps:

1. **The JVM loads code and libraries.** Which classes are actually available depends on the process's artifacts and classpath.
2. **Spring creates the `Environment` and reads configuration sources.** Values can come from files, profiles, environment variables, system properties, or command-line arguments.
3. **Spring discovers bean definitions.** Component scanning finds classes like `@Component`, `@Service`, `@Repository`, and `@Controller` within the scan scope; `@Configuration` classes can define beans explicitly.
4. **Auto-configuration evaluates conditions.** Spring Boot checks whether classes exist, whether user-supplied beans are present, which properties are set, and other criteria before creating matching default configurations.
5. **ApplicationContext initializes beans and required services.** If it is a web application with a matching stack, this includes starting the web server.
6. **The application handles real work.** When an HTTP request arrives, Spring MVC (if present) routes to a controller; business code uses beans, configuration values, and external services.

Thus, `@SpringBootApplication` does not mean "turn on every capability of Spring." Auto-configuration is **conditional configuration**: when a library is missing, a required bean is absent, or a condition fails, the outcome changes.

A key concept worth remembering is the **classpath**: the set of classes and libraries the application can load during a run. Dependencies declared in Maven/Gradle shape the classpath, but only artifacts actually resolved and included in the runtime classpath directly affect the running process.

## 4. End-to-End Example: Same Endpoint, Different Behaviors

Consider a Spring Boot application using Spring MVC. The example below illustrates a common Spring Boot 3.x setup with Java 17 or higher; starter names can differ across major versions, so verify against the version your project uses.

### 4.1. Dependencies Provide HTTP Execution Capability

A Maven project can declare the following dependency in `pom.xml` when appropriate Spring Boot version management is in place:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

A Spring Boot starter typically bundles the libraries needed for a specific purpose. For the traditional web starter in Spring Boot 3.x, that includes Spring MVC components, JSON support, and an embedded servlet server. Underlying libraries are pulled in as **transitive dependencies**, so you do not declare each one individually.

Without an appropriate web stack, code with `@RestController` alone cannot start a working HTTP server. Conversely, adding the starter alone does not create the `/hello` endpoint: that endpoint comes from source code.

### 4.2. Source Code Defines the Endpoint and Uses Configuration

Place the controller in `com.example.demo` or a subpackage so it falls within the component scan scope of `DemoApplication`.

~~~java
package com.example.demo;

import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    private final String greeting;

    public GreetingController(@Value("${app.greeting}") String greeting) {
        this.greeting = greeting;
    }

    @GetMapping("/hello")
    public Map<String, String> hello() {
        return Map.of("message", greeting);
    }
}
~~~

Here:

- `@RestController` lets Spring MVC recognize the request-handling class and write return values to the HTTP response.
- `@GetMapping("/hello")` specifies the path and HTTP GET method.
- `@Value("${app.greeting}")` tells Spring to retrieve the `app.greeting` property from effective configuration and pass it into the constructor.
- `hello()` defines the response payload shape; the web stack's JSON converter serializes the `Map` into JSON.

The **source code** establishes that `GET /hello` returns a JSON object with a `message` key. The **configuration** determines the specific message string.

### 4.3. Default Configuration Supplies Values

Create `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

app:
  greeting: "Hello from default configuration"
~~~

After starting the application, request:

~~~http
GET http://localhost:8080/hello
~~~

Expected result:

~~~json
{
  "message": "Hello from default configuration"
}
~~~

Port `8080` is the value set in YAML and is also the common default port for Spring Boot servlet applications when no other configuration overrides it. If the controller stays unchanged while `app.greeting` changes, the response changes according to the value loaded at startup.

### 4.4. Profiles Select Configuration for the Development Environment

Create an additional file `src/main/resources/application-dev.yml`:

~~~yaml
app:
  greeting: "Hello from dev environment"
~~~

When running the built JAR with the `dev` profile:

~~~bash
java -jar target/app-name.jar --spring.profiles.active=dev
~~~

Expected response for `GET /hello`:

~~~json
{
  "message": "Hello from dev environment"
}
~~~

Here, `application.yml` provides the shared baseline; `application-dev.yml` adds or overrides matching properties when the `dev` profile is active. There is no need to write `if (dev)` branches inside the controller to get a different greeting.

**Distinction:** Spring profiles select groups of beans/configuration at runtime. Maven profiles or similar build mechanisms can alter how the artifact is built and which dependencies are included—a different concept. A Spring profile by itself does not swap artifacts or add libraries to the JAR.

### 4.5. Environment Variables and Runtime Arguments Override Values

On a Bash-style shell, you can run the same JAR with:

~~~bash
APP_GREETING="Hello from environment variable" SERVER_PORT=9090 java -jar target/app-name.jar --spring.profiles.active=dev
~~~

In Spring Boot, the standard environment variable mapping for these properties maps `APP_GREETING` to `app.greeting` and `SERVER_PORT` to `server.port`. Requests to `http://localhost:9090/hello` then return the greeting from the environment variable.

Equivalent example in PowerShell:

~~~powershell
$env:APP_GREETING = "Hello from environment variable"
$env:SERVER_PORT = "9090"
java -jar target/app-name.jar --spring.profiles.active=dev
~~~

The commands above only illustrate passing configuration to the **launched process**. The name `app-name.jar` is a placeholder and should be replaced with your actual built artifact name. Editing a config file packaged inside the JAR or modifying environment variables after the application has started typically does not update running beans automatically; an explicit refresh mechanism or restart is required.

You can also pass a command-line argument:

~~~bash
java -jar target/app-name.jar --server.port=9191
~~~

With Spring Boot's standard default property sources, the command-line argument `--server.port=9191` takes precedence over `SERVER_PORT` if both are present and the application has not customized argument parsing.

### 4.6. Comparing Runs

Assuming every run uses the same Java code and the same JAR artifact containing the controller above:

| Run | Profile | Effective Source of `app.greeting` | Port | Result of `GET /hello` |
|---|---|---|---|---|
| Default | Without `dev` | `application.yml` | 8080 | "Hello from default configuration" |
| Development | `dev` | `application-dev.yml` | 8080 | "Hello from dev environment" |
| Development with env vars | `dev` | `APP_GREETING` | 9090 via `SERVER_PORT` | "Hello from environment variable" |

This table compares only the values listed in the example, assuming no other configuration source overrides them. It illustrates one principle: **keeping source code and dependencies identical while changing configuration or environment can still change behavior**.

## 5. "Effective Configuration" Differs from a Single Config File

In real-world projects, opening `application.yml` and reading a single value can lead to wrong conclusions. Spring Boot can receive the same property key from many sources. The value the application sees is the result after applying configuration loading and precedence rules.

Common sources:

- `application.yml` or `application.properties` packaged inside the app or placed in an external config location.
- Profile-specific files such as `application-dev.yml` and `application-prod.properties`.
- Operating system or container environment variables, e.g., `SPRING_PROFILES_ACTIVE=prod`.
- Java system properties, e.g., `-Dserver.port=9090` placed before `-jar`.
- Command-line application arguments, e.g., `--server.port=9191`.
- Additional sources declared via config import mechanisms or registered in code.

Among common sources in a standard Spring Boot setup, command-line arguments take precedence over Java system properties, Java system properties take precedence over environment variables, and environment variables take precedence over `application.yml`. However, this is **not the entire property source precedence table**: external file locations, profile-specific files, imports, test properties, custom code, and other sources each have specific rules. When you need to determine a property's exact value, inspect the actual loaded sources and the precedence order for your Spring Boot version.

### Profiles Are a Way to Select Configuration Context

A profile like `dev` or `prod` is a configuration label that can be activated via `spring.profiles.active`. It enables applying environment-specific values and beans.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
public class ExampleConfiguration {

    @Bean
    @Profile("dev")
    public DiagnosticService diagnosticService() {
        return new DiagnosticService();
    }
}
~~~

In this example, the bean is created only when the `dev` profile is active (assuming `DiagnosticService` is defined in the project). If other code requires that bean unconditionally in `prod`, the application can fail at startup because the bean cannot be found. This shows how **configuration conditions directly affect the structure of the ApplicationContext**, not just text strings.

Do not treat profiles as a "shortcut" to skip environment checks. Even with `prod` active, a wrong database URL, missing secret, or unreachable external service will still break the application.

### Prefer Structured Configuration

As a group of properties grows, `@ConfigurationProperties` is usually clearer than scattered `@Value` annotations because it binds a group of values into a typed object and supports validation. Example structure:

~~~yaml
app:
  notification:
    enabled: true
    retry-count: 3
    timeout: 5s
~~~

Those keys only take effect when a bean or code actually reads and uses them. Spring Boot does not create business behavior simply because YAML contains `app.notification.enabled`.

## 6. How Do Dependencies Affect Behavior?

### 6.1. Adding Libraries Can Trigger Auto-configuration

Spring Boot uses conditions such as `@ConditionalOnClass`, `@ConditionalOnMissingBean`, and `@ConditionalOnProperty`. Depending on which classes, beans, and properties are present, an auto-configuration can be applied or skipped.

Consider an application working with a relational database:

1. Dependencies related to JDBC or Spring Data place integration classes onto the classpath.
2. An appropriate JDBC driver provides the ability to communicate with the specific database engine.
3. Configuration such as `spring.datasource.url`, username, and credentials specifies the connection target.
4. Auto-configuration evaluates conditions to create beans such as `DataSource` where appropriate; custom-defined beans can replace the default.
5. Networking, DNS, the database server, and actual credentials determine whether connecting succeeds.

An application can **build successfully yet fail at startup** if dependencies are present but the database is unreachable; or it might start up and fail only on the first request touching the database, depending on connection initialization and usage behavior.

### 6.2. Dependency Versions and Scopes Matter Too

Not all library versions are mutually compatible. Maven/Gradle resolves the dependency graph according to build-tool rules and version management mechanisms in the project. Changing a transitive version can change APIs or runtime behavior without editing a single line of Java calling that library.

Errors like `ClassNotFoundException`, `NoClassDefFoundError`, or `NoSuchMethodError` can occur when the runtime classpath lacks a class or contains a different version than compiled code expected. Distinguish:

- **Compile classpath**: classes used for compilation.
- **Runtime classpath**: classes actually present when the application runs.
- **Test classpath**: may include tools or libraries intended solely for testing.

For example, a test-scoped library will not automatically appear on the runtime classpath of the deployed JAR. Likewise, adding a dependency only matters when the newly built artifact actually packages or accesses it.

### 6.3. Your Beans Can Change Defaults

Many auto-configurations only create a default bean when the application has not defined a matching bean. Therefore, two projects with the exact same starters can behave differently if one declares a custom bean.

This also explains why "adding a dependency" does not always mean "Spring Boot turns on the entire feature." Starter names, auto-configuration conditions, custom beans, and controlling properties must be examined together.

## 7. The Runtime Environment Is Part of the Running Application

A JAR artifact can be byte-for-byte identical yet behave differently when executed because surrounding conditions differ.

| Environmental Aspect | Observable Impact | Illustrative Scenario |
|---|---|---|
| Java / JVM version | Bytecode loading, memory flags, runtime behavior | A JAR compiled for a newer Java version cannot run on an older JVM |
| Environment variables & system properties | Override Spring properties or values read directly by code | `SERVER_PORT=9090` changes the server port |
| Network, DNS, and firewall | Reachability of APIs, databases, message brokers | A database hostname only resolves inside a private network |
| File system and permissions | Reading certificates, writing log files, saving uploads | A container process lacks write permission for a directory |
| CPU, RAM, container limits | Response latency, GC pauses, startup survival | Container is terminated for exceeding its memory limit |
| Time zone, locale, and clock | Formatting, scheduling, timestamps | Scheduled job runs in an unexpected time zone |
| External services and data | Business responses and availability | Staging and production databases hold different data |

Pay special attention to the meaning of `localhost`. Inside a container, `localhost` refers to that container itself; inside a VM, it refers to that VM; on a laptop, it refers to that laptop. Thus, `jdbc:postgresql://localhost:5432/...` can work when all services run on one machine and fail once the application moves into its own container.

**A profile does not create a physical environment.** Enabling `prod` does not provision a production database, grant file permissions, or configure networking. Profiles only select Spring configuration and conditions; real infrastructure must still satisfy those requirements.

## 8. Finding Root Causes When Behavior Differs from Expectations

When an application "works on machine A but fails on machine B," a systematic investigation checks four questions in order instead of randomly tweaking YAML files.

### 8.1. Are We Truly Running the Same Code and Artifact?

Verify the commit, build, application version, and packaging being executed. If you just edited a controller but are still running an old JAR, code changes cannot show up. If different builds are used, included dependencies may differ too.

Example commands to inspect dependencies depending on the project's build tool:

~~~bash
./mvnw dependency:tree
./gradlew dependencies --configuration runtimeClasspath
~~~

These are reference commands to help learners see how to inspect the dependency graph; use the command appropriate for your Maven or Gradle project.

### 8.2. Which Configuration Values Were Actually Loaded?

Cross-check active profiles, packaged configuration files, external files, environment variables, system properties, and command-line arguments. For the endpoint example above, trace the effective source of `app.greeting` and `server.port`.

Startup logs and observability tools can provide useful evidence. If the application enables Spring Boot Actuator, certain management endpoints can display configuration or auto-configuration conditions; restrict access and avoid exposing sensitive values.

### 8.3. Do the Classpath and Beans Match?

If the server does not start, a bean is missing, or a library method does not exist, check starters, dependency scopes, transitive versions, component scan boundaries, and `@Conditional...` conditions. With auto-configuration, what matters is **which conditions matched or failed**, not just "whether a dependency was written in the build file."

### 8.4. Does the Environment Meet Requirements?

Check port availability, resources, permissions, network connectivity, hostnames, DNS, certificates, secrets, and external service health. When a request reaches the application and fails during processing, the outcome can also depend on request input or database state at that moment.

Common symptoms:

| Symptom | Areas to Check First | Why? |
|---|---|---|
| `GET /hello` returns 404 | Source code, package/component scan, web dependency | Endpoint may not be registered or request path is wrong |
| Port differs from `8080` | Effective properties, runtime arguments, env vars | `server.port` may be overridden |
| App reports missing bean | Component scan, profile config, auto-configuration, dependencies | Bean may not be created because a condition was not met |
| Missing class or method error | Artifact, versions, and runtime classpath | Required library may be missing or incompatible |
| Fails only inside a container | Networking, `localhost`, DNS, file permissions, resources | Containers have an isolated environment compared to local dev machines |
| Cannot connect to database | URL/credentials/driver and database status, network | Requires valid configuration, libraries, and infrastructure together |

## 9. Designing for Predictable Behavior

Keeping all four factors clear leads to more reliable application design and deployment:

1. **Keep logic in source code and use configuration for environment-varying values.** For example, endpoints and business rules live in Java, while database URLs, ports, timeouts, or business thresholds are declared via appropriate properties.
2. **Manage dependencies consistently.** Use Spring Boot-compatible version management and produce traceable artifacts. Avoid changing transitive versions arbitrarily.
3. **Use profiles intentionally.** Clearly distinguish shared values from `dev`, `test`, and `prod` overrides; never assume a profile name guarantees environment quality or safety.
4. **Supply sensitive configuration from secure sources.** Never commit passwords, tokens, or secret keys to the repository. Use environment variables or a secret manager as appropriate for the platform, and control read access and logging.
5. **Prefer deploying the same artifact across environments when possible.** Behavioral differences then become easier to trace to configuration and runtime conditions; keep in mind that external environments and data still differ.
6. **Observe enough information to diagnose issues.** Record build version, active profiles, external dependency status, and concrete errors, without printing secrets into logs.

Avoid two common mistakes. First, **configuration does not generate processing code**: adding a new property only has an effect if the framework or code reads it. Second, **dependencies do not replace infrastructure**: adding a new driver or starter does not spin up an external database or open network access.

When analyzing any Spring Boot behavior, identify *which code handles it*, *which classes and beans exist*, *which properties actually take effect*, and *what conditions the process is running under*. These four questions connect how Spring Boot boots up to the behavior end users observe.
