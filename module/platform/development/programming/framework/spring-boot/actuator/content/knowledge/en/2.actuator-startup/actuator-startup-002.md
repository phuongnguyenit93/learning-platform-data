# Role of the actuator and actuator-autoconfigure modules

You add the Actuator dependency, start the application, and see several management access points appear. Behind that experience lie two tasks: providing the data types and execution code, and configuring them into components suited to the running application.

In Spring Boot 3.3, the two main artifacts serving these two tasks are `spring-boot-actuator` and `spring-boot-actuator-autoconfigure`. Understanding the boundary between them helps you read dependencies, diagnose missing beans, and avoid confusing having the library with having exposed a URL.

Here, "module" refers to a library component packaged as a Spring Boot artifact/JAR. It does not mean each application must create two separate Gradle projects or two separate processes.

## 1. The big picture

| Component | Question it answers | Examples |
| --- | --- | --- |
| `spring-boot-actuator` | What operational capabilities, APIs, and implementations are available to use? | `Health`, `HealthIndicator`, `HealthEndpoint`, endpoint infrastructure |
| `spring-boot-actuator-autoconfigure` | When and how are those capabilities configured for this application? | `HealthEndpointAutoConfiguration`, properties, and integration configurations |
| `spring-boot-starter-actuator` | What entry point should be used to declare the common dependency set? | Brings the related libraries into the dependency graph |

Spring Boot recommends adding `spring-boot-starter-actuator` to use operational features. You usually do not have to manually declare each underlying JAR. See [Spring Boot 3.3 — Enabling Production-ready Features](https://docs.spring.io/spring-boot/3.3/reference/actuator/enabling.html).

One way to visualize it:

```text
Add starter to dependencies
             ↓
Actuator and auto-configuration classes are on the classpath
             ↓
Application enables auto-configuration mechanism
             ↓
Configurations are evaluated against conditions
             ↓
Matching beans are registered into the ApplicationContext
             ↓
If web/JMX infrastructure and matching exposure policy exist:
management operations are exposed via the corresponding mechanism
```

**Classpath** is the set of locations where the JVM searches for classes and resources. A **bean** is an object managed by Spring inside the **ApplicationContext**, which is the context holding the application's configuration and components. A library providing a class does not mean Spring has created an instance of that class.

## 2. spring-boot-actuator: APIs and implementation code for operational capabilities

The artifact `org.springframework.boot:spring-boot-actuator` contains the types that Actuator features use at runtime. For health checks, you commonly encounter:

- `Health`: represents a health result.
- `HealthIndicator`: interface for a health check.
- `HealthEndpoint`: endpoint implementation that reads health information.

For example, `HealthEndpoint` belongs to package `org.springframework.boot.actuate.health`, has `@Endpoint(id = "health")`, and read operation `health()`. Its API definition is presented in [HealthEndpoint — Spring Boot 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthEndpoint.html).

### 2.1. Capability to use and managed objects are two different things

A custom check can use the `HealthIndicator` API to return a result. However, merely writing a class or creating a lambda expression does not make the application automatically know to collect its result.

You must register that component with Spring or wire it into the appropriate infrastructure. Next, an endpoint is needed to consume the check components. Only then do you consider the out-of-process access path.

An analogous example in ordinary Java code: having an `InvoiceService` class on the classpath does not cause the program to automatically instantiate an invoice service and invoke it. Spring needs configuration to know what to create and what to wire together.

### 2.2. Actuator contains both infrastructure and adapters, not just data types

Do not view `spring-boot-actuator` as a JAR containing only interfaces or only protocol-independent endpoints. It also contains infrastructure code to discover, execute, and integrate endpoints.

For instance, `WebMvcEndpointHandlerMapping` belongs to package `org.springframework.boot.actuate.endpoint.web.servlet`. This is the implementation that maps endpoints over HTTP using Spring MVC. See [WebMvcEndpointHandlerMapping — API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/servlet/WebMvcEndpointHandlerMapping.html).

Therefore, the main boundary is **capabilities and implementations** versus **auto-configuration to integrate them**. Do not use a rule like "has the word web so it must belong to actuator-autoconfigure" to guess a class's location.

### 2.3. Having the JAR does not mean every feature runs

A non-web application can still use Actuator types. A web application also does not necessarily expose every endpoint.

A feature may require additional libraries, collaborating beans, or configuration. Check the requirements of the specific feature rather than treating a single JAR as an on-switch for all operational capabilities.

## 3. spring-boot-actuator-autoconfigure: conditional configuration

The artifact `org.springframework.boot:spring-boot-actuator-autoconfigure` integrates Actuator capabilities into a Spring Boot application. It contains the auto-configuration classes and related configuration types.

Auto-configuration is enabled by the application via `@EnableAutoConfiguration` or `@SpringBootApplication`. Spring Boot inspects the current dependencies and conditions to decide which configurations apply. See [Spring Boot 3.3 — Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html).

### 3.1. Automatic does not mean unconditional

Questions that may be evaluated when checking configuration include:

| Condition category | Typical question |
| --- | --- |
| Class on classpath | Is the library required by the feature present? |
| Bean in context | Is the required component or a user-supplied component already present? |
| Configuration property | Is the feature enabled by the current configuration? |
| Application type | Is this an appropriate web environment? |
| Endpoint availability | Is the endpoint enabled and exposed under the evaluated policy? |

Each configuration has its own set of conditions. Do not infer that every auto-configuration class uses all conditions in the table.

Changing dependencies, adding beans, or changing properties can cause a configuration to match or not match the next time the context is created. This is a configuration mechanism at application startup, not a background process continuously scanning JARs to arbitrarily replace beans.

### 3.2. The health example

`HealthEndpointAutoConfiguration` belongs to package `org.springframework.boot.actuate.autoconfigure.health`. The class API shows that it:

- Is an `@AutoConfiguration`.
- Uses `@ConditionalOnAvailableEndpoint` for `HealthEndpoint`.
- Enables binding of `HealthEndpointProperties`.
- Imports configurations related to health and corresponding extensions.

See [HealthEndpointAutoConfiguration — API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/health/HealthEndpointAutoConfiguration.html).

As a result, the `HealthEndpoint` class in the implementation JAR is configured with the application's concrete components and policies. Both JARs participate in one feature while doing different parts of the work.

### 3.3. "Available" is a configuration condition, not a network call result

In Spring Boot 3.3, `@ConditionalOnAvailableEndpoint` evaluates endpoint enablement and exposure policy for the relevant technology. It does not send an outbound HTTP request to test whether a URL is reachable. See [ConditionalOnAvailableEndpoint — API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/endpoint/condition/ConditionalOnAvailableEndpoint.html).

After configuration matches, a real URL still requires serving infrastructure, mapping, and appropriate access permissions. Conversely, a context test without a web server can still verify whether an endpoint bean is created.

### 3.4. Web configuration is a separate integration layer

`WebEndpointAutoConfiguration` has a web-environment condition and configures components supporting discovery, name mapping, and filtering of web endpoints. See [WebEndpointAutoConfiguration — API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/endpoint/web/WebEndpointAutoConfiguration.html).

At this point, separate three questions:

```text
Is the HealthEndpoint class present?
        ↓
Does this context have a HealthEndpoint bean?
        ↓
Does this application have an accessible HTTP path to it?
```

Each question requires a different kind of evidence. Finding the class name in a JAR only answers the first question.

## 4. Why does the starter exist?

The starter is a convenient dependency declaration point. It helps the application pull in the commonly used set of libraries without manually maintaining the version list and transitive dependencies.

In Spring Boot 3.3.5, the Actuator starter depends on the base starter, `spring-boot-actuator-autoconfigure`, and related Micrometer components. See [the official starter dependency declaration at v3.3.5](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.5/spring-boot-project/spring-boot-starters/spring-boot-starter-actuator/build.gradle).

A simplified part of the graph, without listing every edge:

```text
spring-boot-starter-actuator
├─ spring-boot-starter
├─ spring-boot-actuator-autoconfigure
│  ├─ spring-boot-actuator
│  ├─ spring-boot
│  └─ spring-boot-autoconfigure
└─ Related Micrometer dependencies
```

The portion beneath the starter is verified from the packaged POM of Spring Boot 3.3.5. This path explains why declaring the starter brings both main JARs onto the classpath even though you wrote only a single dependency line.

### 4.1. Three similar names with different roles

- `spring-boot-autoconfigure`: Spring Boot's general auto-configuration infrastructure and set of configurations.
- `spring-boot-actuator-autoconfigure`: auto-configuration set for Actuator capabilities.
- `spring-boot-starter-actuator`: convenient dependency bundle for using Actuator.

Do not omit an artifact just because another artifact also contains `autoconfigure`. Read the full name and dependency path.

In a project with Spring Boot version management already configured, the standard declaration is:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

This starter does not provide a complete web application by itself. If the goal is HTTP, the application still needs a web foundation and an appropriate startup setup. For an existing web application, there is no need to add a second management application just to use Actuator.

### 4.2. Keeping versions consistent

In a real application, use Spring Boot's dependency management mechanism so components have compatible versions. Do not pin actuator alone to a different version just to fix a missing-class error without understanding the conflict.

Artifact names, dependency edges, and internal details may change between Spring Boot lines. This lesson explains Spring Boot 3.3; when upgrading versions, cross-check the target version's documentation.

## 5. From configuration candidates to actual beans

Spring Boot locates auto-configuration candidates via the resource:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

This resource contains configuration class names. Conditions determine which candidates apply in a specific application; it is not a list of every bean guaranteed to exist. The mechanism and conditional annotations are presented in [Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html).

In `spring-boot-actuator-autoconfigure-3.3.5.jar`, `org.springframework.boot.actuate.autoconfigure.health.HealthEndpointAutoConfiguration` is present in the candidate list. This allows Boot's mechanism to find the configuration without you having to scan all internal packages with `@ComponentScan`.

### 5.1. When the application provides its own components

Some default beans are created under `@ConditionalOnMissingBean`: created only when no matching bean exists yet. Thus, a user-provided bean can cause the default configuration to back off.

You need to read the specific condition to know which part backs off. Adding a business `HealthIndicator` usually adds a source of check results; it does not mean replacing the entire `HealthEndpoint` or turning off all of Actuator.

Also distinguish conditional configuration back-off from allowing two beans with the same name to override each other. Those two mechanisms are not the same. See the exact condition in [ConditionalOnMissingBean — API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html).

### 5.2. Do not use internal details as the default extension point

You can read auto-configuration to understand the application. When customizing, prefer published properties and extension APIs.

Do not directly call an internal factory method of a configuration class just because it helps create an object in an example. The official API notes that auto-configuration class names are intended for exclusion; internal structures are not considered stable public APIs.

The next section only uses a configuration class name to identify which JAR it comes from. The program enables auto-configuration through the standard mechanism without calling internal methods of that class.

## 6. Experiment: same classpath, different context outcomes

We create three contexts in sequence:

1. `plain`: registers a health check without enabling auto-configuration.
2. `auto`: keeps that check and enables `@EnableAutoConfiguration`.
3. `disabled`: enables auto-configuration but sets `management.endpoint.health.enabled=false`.

All three use the same classpath. This lets you observe bean differences without deleting JARs or changing multiple dependencies at once.

### 6.1. Preparing a separate test project

Use JDK 17 or higher and a compatible Gradle version. Spring Boot version 3.3.5 is pinned so JAR file names are easy to reproduce.

Create `settings.gradle`:

```groovy
rootProject.name = 'actuator-module-demo'
```

Create `build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.5')
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}

tasks.register('copyDemoLibraries', Copy) {
    from configurations.runtimeClasspath
    into layout.projectDirectory.dir('lib')
}
```

This is a small Java project using the Spring Boot BOM to manage dependencies. It does not use the Boot packaging plugin, does not add a web starter, and does not start an HTTP server on its own.

To avoid mixing JARs from multiple attempts, use a fresh directory for this experiment. The dependency download task requires network access if libraries are not already cached.

### 6.2. Complete program

Create file `src/main/java/lab/actuator/ActuatorModuleDemo.java`:

```java
package lab.actuator;

import java.nio.file.Path;
import java.util.Map;

import org.springframework.boot.actuate.autoconfigure.health.HealthEndpointAutoConfiguration;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.MapPropertySource;

public class ActuatorModuleDemo {
    public static void main(String[] args) throws Exception {
        System.out.println("api.jar=" + jarName(Health.class));
        System.out.println("config.jar="
                + jarName(HealthEndpointAutoConfiguration.class));
        run("plain", false, true);
        run("auto", true, true);
        run("disabled", true, false);
    }

    private static String jarName(Class<?> type) throws Exception {
        return Path.of(type.getProtectionDomain()
                .getCodeSource().getLocation().toURI())
                .getFileName().toString();
    }

    private static void run(String label, boolean auto, boolean enabled) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext()) {
            context.getEnvironment().getPropertySources().addFirst(
                    new MapPropertySource("demo", Map.of(
                            "management.endpoint.health.enabled",
                            Boolean.toString(enabled),
                            "management.health.defaults.enabled", "false")));
            context.register(HealthConfig.class);
            if (auto) {
                context.register(BootConfig.class);
            }
            context.refresh();

            Map<String, HealthEndpoint> endpoints =
                    context.getBeansOfType(HealthEndpoint.class);
            System.out.println(label + ".endpoints=" + endpoints.size());
            if (!endpoints.isEmpty()) {
                HealthEndpoint endpoint = endpoints.values().iterator().next();
                System.out.println(label + ".status="
                        + endpoint.health().getStatus().getCode());
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class HealthConfig {
        @Bean
        HealthIndicator labHealthIndicator() {
            return () -> Health.up().build();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    static class BootConfig {
    }
}
```

In this code:

- `HealthConfig` is a configuration we wrote, registering `labHealthIndicator`.
- `BootConfig` enables the standard auto-configuration mechanism.
- Properties are added to the environment before `refresh()` so condition evaluation sees the right values.
- `management.health.defaults.enabled=false` keeps the experiment focused on the check we registered, rather than depending on default machine checks.
- `jarName` reads where the class was loaded from to identify the artifact, without using it to alter configuration.

The two contexts with auto-configuration are created independently and closed after inspection. The program does not mutate properties on a running context to ask it to recreate all beans.

### 6.3. Compile and run

In the experiment root directory, using PowerShell:

```powershell
gradle copyDemoLibraries
javac -encoding UTF-8 -cp "lib/*" -d out src/main/java/lab/actuator/ActuatorModuleDemo.java
java -cp "out;lib/*" lab.actuator.ActuatorModuleDemo
```

If the test project has a Gradle Wrapper, you can use that wrapper instead of the `gradle` command. On Linux/macOS, the run command uses `:` as the classpath separator:

```bash
java -cp "out:lib/*" lab.actuator.ActuatorModuleDemo
```

Expected stdout of the program in the experiment setup:

```text
api.jar=spring-boot-actuator-3.3.5.jar
config.jar=spring-boot-actuator-autoconfigure-3.3.5.jar
plain.endpoints=0
auto.endpoints=1
auto.status=UP
disabled.endpoints=0
```

Gradle download or execution messages are not part of the Java program's illustrative stdout. If you change library versions, the two JAR name lines should reflect the versions actually loaded.

### 6.4. Reading each result as evidence

| Output line | What it proves in the experiment |
| --- | --- |
| `api.jar=...` | The `Health` class was loaded from the Actuator implementation JAR |
| `config.jar=...` | The health configuration class was loaded from the actuator-autoconfigure JAR |
| `plain.endpoints=0` | Merely having the classes and an indicator does not make the context create an endpoint |
| `auto.endpoints=1` | Auto-configuration registered the endpoint when conditions matched |
| `auto.status=UP` | The endpoint read a healthy result from the simulated check |
| `disabled.endpoints=0` | Disabling health via property prevented the endpoint configuration branch from applying |

Both JARs can still load classes across all three runs. Therefore, you must not explain `disabled.endpoints=0` as "the JVM unloaded the HealthEndpoint class from memory" or "the Actuator dependency disappeared".

### 6.5. What the experiment has not tested

The program uses a plain `AnnotationConfigApplicationContext`. It does not create web infrastructure and does not open a port. Hence, `auto.endpoints=1` does not prove `http://localhost:8080/actuator/health` is reachable.

`labHealthIndicator` always returns `Health.up()` to isolate the registration mechanism. This result also does not check a database, message queue, or business correctness.

We are observing bean configuration, not testing the full deployment behavior of a web application. When HTTP needs to be verified, you must use an appropriately configured web application and inspect the real response.

### 6.6. One change to self-verify

In a copy of the experiment, change the printed label of the third run to distinguish it easily, then keep `enabled=true` instead of `false` for that run. Predict the endpoint count before running.

If other conditions remain unchanged, the third run will have an endpoint just like the `auto` branch. Then restore the code to compare. This exercise helps you verify the relationship between input properties and context creation results, rather than memorizing a single number.

## 7. From bean to HTTP: additional checks needed

In a real Spring Boot web application, the path also includes integration layers:

```text
Endpoint implementation class is on the classpath
                  ↓
Bean creation conditions match
                  ↓
Endpoint bean exists in the context
                  ↓
Web endpoint discovery and exposure infrastructure
                  ↓
Mapping on the application's HTTP server
                  ↓
Security filters and network path allow access
```

The diagram is the order of questions to check, not a strict description of the exact initialization order of every bean.

Example properties serving two different purposes in Spring Boot 3.3:

```yaml
management:
  endpoint:
    health:
      enabled: true
  endpoints:
    web:
      exposure:
        include: "health"
```

The first property controls enabling health; the second selects the access point exposed over HTTP. An exposure choice neither supplies missing dependencies nor replaces Spring Security permissions. Policy details are described in [Spring Boot 3.3 — Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

For a web application running on the default port and path, you can check:

```powershell
curl.exe -i "http://localhost:8080/actuator/health"
```

Read the actual HTTP code and body. If the application changes port, path, or uses authentication, you must use the corresponding values. This command is for a separate running web application; it cannot call the console program in section 6 because that program already closed its context and has no server.

### 7.1. Distinguishing three types of missing components

**Missing class:** code requires a type, but that type is absent from the runtime classpath. Check dependencies and versions.

**Missing bean:** the class can be loaded, but the context lacks the corresponding managed object. Check configuration registration, conditions, properties, and user-supplied components.

**Missing access path:** the application-side component exists, but it is unreachable at the expected URL. Check web application, exposure, mapping, permissions, port, and network.

Do not use a single HTTP error to immediately conclude a JAR is missing. Conversely, finding the JAR in dependencies is not enough to rule out a bean creation failure.

## 8. Reading dependencies and condition reports to find root causes

### 8.1. Verifying which libraries were actually selected

In a Gradle project, you can run:

```powershell
gradle dependencies --configuration runtimeClasspath
gradle dependencyInsight --dependency spring-boot-actuator --configuration runtimeClasspath
gradle dependencyInsight --dependency spring-boot-actuator-autoconfigure --configuration runtimeClasspath
```

In a multi-module project, run against the right application project. Distinguish the dependency you declared from the final version Gradle resolved.

If `NoClassDefFoundError` or `NoSuchMethodError` occurs, record the class/method name and the present versions. Do not start by adding both artifacts with random versions.

An application can compile with one set of dependencies yet run with another, for example due to packaging configuration or the runtime environment. So when needed, compare the actual artifact being executed as well.

### 8.2. Seeing why configurations matched or did not match

For an application started via `SpringApplication`, the `--debug` option displays the condition evaluation report. For example with an application JAR:

```powershell
java -jar app.jar --debug
```

`app.jar` is an example name; replace it with the real application's JAR. This is not a command for the compiled console class file from section 6.

Locate the relevant configuration such as `HealthEndpointAutoConfiguration` and read the specific conditions. The report is not a table where "every non-matching line is an error": many non-matching branches are normal because the application does not use those libraries or technologies.

If appropriate access is already configured, the `conditions` endpoint also helps inspect configuration decisions. There is no need to expose all endpoints just to investigate one case.

### 8.3. Identifying the smallest change to verify

| Symptom | Evidence to check | Verification direction |
| --- | --- | --- |
| Code cannot find `Health` | Compile classpath | Was the Actuator dependency resolved? |
| `HealthEndpoint` class exists but no bean | Configuration and condition report | Is auto-configuration enabled, is health disabled? |
| Custom bean changes default behavior | Actual beans and missing-bean condition | Which component is being used instead of the default? |
| HTTP returns 404 | Endpoint, path, and application type | Is there web infrastructure and exposure on the path being called? |
| HTTP returns 401/403 | Security policy | Does the caller have permission under the current mechanism? |
| Adding property has no effect | Effective configuration value | Wrong profile or overridden by another configuration source? |

HTTP status codes are investigation starting points, not guaranteed mappings for every system with custom proxies and security rules.

Good practice is to state a hypothesis, change one controlled factor, and re-read the evidence. For example, the experiment in section 6 keeps the classpath fixed to focus on testing the role of auto-configuration and the health property.

## 9. Misconceptions to correct

### "actuator-autoconfigure is only a compile-time dependency"

Configuration classes are used when the application creates its context. If you rely on them at runtime, they must be on the runtime classpath. Do not exclude them from packaging just because the name contains "configure".

### "actuator only contains interfaces; all runtime code lives in autoconfigure"

Actuator contains both APIs and implementations, including technology-specific adapters. Auto-configuration creates and wires the appropriate components. Full package names and class loading locations are better evidence than guessing from short names.

### "With actuator-autoconfigure, actuator is not needed"

In the Spring Boot 3.3.5 graph, the configuration artifact depends on the implementation artifact. It does not replace classes like `HealthEndpoint`. You may declare only one artifact while the other is pulled in transitively; inspect the graph before concluding.

### "The starter is where all endpoint classes live"

The starter is primarily a dependency bundle entry point. In the experiment, `Health` and the configuration class were loaded from two separate JARs, not from `spring-boot-starter-actuator`.

### "A custom indicator turns off all Actuator configurations"

An indicator is a health check source. Default configuration back-off depends on the bean type and specific conditions; it does not apply globally to the whole feature just because the application has one custom bean.

### "Enabling an endpoint lets outsiders access it"

The non-web experiment still creates the endpoint bean. For a real HTTP path, web infrastructure, exposure policy, mapping, and permissions are also required. Use the right evidence for each layer.

## 10. Self-check

### Scenario A

You find `HealthEndpoint.class` in the JAR, yet a context manually created with plain Spring has no `HealthEndpoint` bean.

**Explanation:** that only confirms the class exists. You need to check the registration and configuration mechanism. The `plain` experiment shows that having the library does not automatically mean having the bean.

### Scenario B

Two applications use the same starter and same version, yet only one application has the expected endpoint.

**Explanation:** compare effective properties, context type, conditions, application-supplied components, and startup mechanism. Identical dependencies do not guarantee identical runtime configuration.

### Scenario C

You want to close an HTTP management path and are about to exclude the entire `spring-boot-actuator-autoconfigure`.

**Explanation:** excluding the JAR affects many configurations, not just that path. First identify whether the requirement is disabling the capability, changing exposure policy, or changing access permissions; use the mechanism matching the actual requirement.

### Applied exercise

Choose one Actuator capability currently in use and answer:

1. Which artifact and package does the main implementation type belong to?
2. What is the name of the related auto-configuration class?
3. Which conditions are significant in the current application?
4. Which beans actually exist in the context?
5. If external access is needed, which mechanism exposes it and who is allowed to call it?

You understand the relationship between the two modules when you can explain the path from dependency to class, from configuration to bean, and from bean to usage in a concrete application.
