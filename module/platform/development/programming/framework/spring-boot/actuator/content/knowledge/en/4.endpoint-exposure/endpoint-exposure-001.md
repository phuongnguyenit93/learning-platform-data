# Enabling or Disabling Individual Endpoints with `management.endpoint.<id>.enabled`

In the **Endpoint Exposure** group, the first question to answer is: does the application allow that endpoint to be active or not? The `management.endpoint.<id>.enabled` property controls this decision for each Actuator endpoint.

This article uses **Spring Boot 3.3.x**; the complete example fixes **3.3.13, JDK 21, and Gradle 8.5**. The hands-on results below are the expected results with the exact sample configuration and do not apply mechanically to applications that have added security filters or customized Actuator.

## 1. Understanding What Is Being Enabled or Disabled

An Actuator endpoint is a management capability with an identifier, such as `health`, `info`, `metrics`, or `loggers`. This identifier is used in the property name:

```properties
management.endpoint.info.enabled=true
management.endpoint.metrics.enabled=false
```

These two lines allow the `info` endpoint to be active and disable the `metrics` endpoint. `<id>` is the placeholder to replace with the actual identifier; do not write literal `<` and `>` characters into the configuration.

The identifier is different from the HTTP path. With the default base path, `info` corresponds to `/actuator/info`; when changing the exposed path, the enable/disable property still uses `info`. Nor does this property control a business `@RestController`, such as `/orders`.

Three questions must be distinguished:

| Question | Related configuration or mechanism | Meaning |
| --- | --- | --- |
| Is the endpoint enabled? | `management.endpoint.<id>.enabled` | Enables or disables that endpoint |
| Is the endpoint exposed over HTTP? | `management.endpoints.web.exposure.include/exclude` | Selects the endpoints exposed over HTTP |
| Does the caller have permission to invoke it? | Security configuration, e.g., `SecurityFilterChain` | Controls authentication and authorization |

You can remember the processing flow using the three questions above, though this is not a description of the execution order of all HTTP filters. In Spring Boot 3.3, an endpoint is considered available when it is enabled and exposed via a suitable technology. Auto-configuration conditions must also be satisfied. [Actuator 3.3 Documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)

## 2. Writing Configuration for the Right Endpoint

### 2.1. Properties and YAML Syntax

Properties format:

```properties
management.endpoint.info.enabled=true
management.endpoint.loggers.enabled=false
```

Equivalent YAML format:

```yaml
management:
  endpoint:
    info:
      enabled: true
    loggers:
      enabled: false
```

Choose one format for the same configuration location. The two blocks above are alternative representations of each other.

Distinguish singular and plural:

- `management.endpoint`: per-endpoint configuration, e.g., `info.enabled`.
- `management.endpoints`: common configuration for the set of endpoints, e.g., `enabled-by-default` or `web.exposure.include`.

Therefore, `management.endpoints.info.enabled` uses the wrong branch. Do not expect Spring Boot to always report an error for every misspelled property; a key not used by the corresponding mechanism may fail to produce the intended effect.

Some common IDs are listed in the properties appendix, such as `health`, `info`, `loggers`, `metrics`, and `shutdown`. Use the exact ID: `loggers`, not `logger`. [Spring Boot 3.3 Configuration Properties Appendix](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html)

### 2.2. When No Individual Property Is Specified

The `@Endpoint` declaration has an `enableByDefault` attribute to describe the endpoint's default choice. The default value of this annotation attribute is `true`; an endpoint can declare otherwise. This is a default layer, not a command forcing it to always be enabled. [API of `@Endpoint`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/annotation/Endpoint.html)

For Spring Boot 3.3 built-in endpoints, when no overriding configuration is set, `shutdown` is disabled by default; the remaining endpoints are enabled by default. That does not guarantee all of them have HTTP URLs or are created in every application: some endpoints require additional libraries, beans, or setup. [Built-in Endpoints and Related Conditions](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints)

## 3. Individual Configuration Takes Precedence Over the Global Default

Spring Boot 3.3 determines the enabled state in the following order:

1. If `management.endpoint.<id>.enabled` is present, use that value.
2. If no individual value is present but `management.endpoints.enabled-by-default` is present, use the global value.
3. If neither is set, use the endpoint's `enableByDefault`.

This table applies to the enablement decision, without yet considering exposure, libraries, or security:

| Global value | Individual value | Endpoint | Enabled result |
| --- | --- | --- | --- |
| Unset | Unset | `info` | `true` per the endpoint's default |
| Unset | Unset | `shutdown` | `false` per the endpoint's default |
| `false` | Unset | `info` | `false` |
| `false` | `true` | `info` | `true` |
| `true` | `false` | `info` | `false` |
| `true` | Unset | `shutdown` | `true` |

An easily overlooked point is that **explicitly setting the global value to `true` differs from leaving it unset** for an endpoint whose own default is `false`, such as `shutdown`.

These are two different keys with a specific/global precedence rule, not a comparison of which line appears where in a file. [Endpoint Enablement Decision Source Code in 3.3.13](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/endpoint/condition/OnAvailableEndpointCondition.java)

### 3.1. Choosing the Configuration Approach Based on Need

If you only want to disable one specific capability, you can set:

```properties
management.endpoint.loggers.enabled=false
```

If you want to enable only explicitly selected endpoints, use:

```properties
management.endpoints.enabled-by-default=false
management.endpoint.health.enabled=true
management.endpoint.info.enabled=true
management.endpoints.web.exposure.include=health,info
```

In the second example:

- The first line sets the global default to disabled.
- The next two lines re-enable `health` and `info`.
- The last line selects these two IDs to expose over HTTP.

Read each line according to its responsibility. Adding `metrics` to the exposure list in this example is not enough to enable `metrics`; using it also requires the appropriate enablement configuration.

## 4. Disabling an Endpoint Affects Auto-configuration

Endpoints auto-configured by Spring Boot use conditions to decide whether to register their beans. For example, `InfoEndpointAutoConfiguration` uses `@ConditionalOnAvailableEndpoint(endpoint = InfoEndpoint.class)` and only creates `InfoEndpoint` when the condition matches.

Therefore, when `management.endpoint.info.enabled=false`, in standard auto-configuration, you should not imagine that a URL still exists and merely returns a "disabled" message. The corresponding endpoint bean is not auto-configured. Requiring injection of this bean into another component can prevent the application from starting if the bean is no longer present. [Auto-configuration of `InfoEndpoint`](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/info/InfoEndpointAutoConfiguration.java)

Two boundaries must be kept clear:

- Enabling an endpoint does not replace other bean creation conditions. For example, `MetricsEndpoint` configuration also requires a `MeterRegistry`.
- Disabling `metrics` disables that metrics-reading endpoint; it does not mean disabling all of Micrometer, all meters, or every metric export mechanism.

You can see this separation in `MetricsEndpointAutoConfiguration`: the endpoint auto-configuration class runs after the metrics system auto-configuration classes and has its own condition on `MeterRegistry`. [Auto-configuration of `MetricsEndpoint`](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/MetricsEndpointAutoConfiguration.java)

The bean explanation here refers to endpoints auto-configured by Spring Boot under standard conditions. Do not overgeneralize this into a claim that changing a property will automatically delete every bean registered by application authors in any arbitrary way.

## 5. Hands-on: Observing Beans and HTTP Before and After Disabling

The goal is to change exactly one property of `info`, keep the exposure list unchanged, and then compare two pieces of evidence:

1. Whether Spring has the `InfoEndpoint` bean or not.
2. What result an HTTP request to `/actuator/info` receives.

The example is a standalone Gradle project. It requires JDK 21, Gradle 8.5, and an internet connection to download dependencies on the first run. Only Web and Actuator are declared; no Spring Security, custom endpoints, or HTTP filters are added. The application listens on the local address `127.0.0.1:8087`.

### 5.1. Creating the Minimal Project

Structure:

```text
endpoint-enable-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/EndpointEnableApplication.java
    └── resources/application.properties
```

File `settings.gradle`:

```groovy
rootProject.name = 'endpoint-enable-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

File `src/main/java/example/EndpointEnableApplication.java`:

```java
package example;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.info.InfoEndpoint;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class EndpointEnableApplication {

    public static void main(String[] args) {
        SpringApplication.run(EndpointEnableApplication.class, args);
    }

    @Bean
    ApplicationRunner reportInfoEndpoint(ObjectProvider<InfoEndpoint> provider) {
        return args -> System.out.println(
                "INFO_ENDPOINT_BEAN_PRESENT=" + (provider.getIfAvailable() != null));
    }
}
```

`ObjectProvider` allows the example to check whether the bean is present without requiring the bean to exist for startup. This printed line is an observation aid for the lab, not a feature to add to every real-world application.

File `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8087
spring.jmx.enabled=false

management.endpoints.enabled-by-default=false
management.endpoint.health.enabled=true
management.endpoint.info.enabled=true
management.endpoints.web.exposure.include=health,info
```

JMX is disabled in the example so that we only observe the HTTP exposure path.

### 5.2. Case A: Enabling `info`

In the project directory, compile, package, and run:

```powershell
gradle bootJar
java -jar build/libs/endpoint-enable-demo-1.0.0.jar
```

If the project already has Gradle Wrapper 8.5, you can replace the first command with `.\gradlew.bat bootJar`. Do not use `javac` directly for this example because the code requires Spring libraries; Gradle provides the dependency classpath and builds an executable JAR.

Among the stdout lines during startup, the line printed by the sample program is:

```text
INFO_ENDPOINT_BEAN_PRESENT=true
```

Open a second PowerShell window and check the HTTP status code. Use `curl.exe` to invoke the cURL tool on Windows:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/actuator/info
```

Expected output:

```text
200
```

The bean is present, the endpoint is exposed, and the sample project has no security layer blocking the request. Returning an empty JSON object from `info` when no contributors provide data does not mean the endpoint is disabled.

### 5.3. Case B: Disabling `info` While Keeping Exposure Unchanged

Stop run A with `Ctrl+C`. Run that same JAR again with the argument:

```powershell
java -jar build/libs/endpoint-enable-demo-1.0.0.jar --management.endpoint.info.enabled=false
```

This argument changes the effective value of the individual key from `true` in the file to `false`. The `health,info` list remains unchanged.

Observed line at startup:

```text
INFO_ENDPOINT_BEAN_PRESENT=false
```

Call again:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/actuator/info
```

Expected output:

```text
404
```

In this exact sample project, this path has no endpoint to handle it, even though the `info` ID is still in the exposure list. You can verify the application still serves another endpoint:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/actuator/health
```

With the sample application healthy, the expected output is:

```text
200
```

If a real service has a health component reporting an error, `health` may return a different code; the HTTP status code of `health` does not depend solely on enabling the endpoint.

### 5.4. Case C: Re-enabling via Individual Configuration

Stop run B and run:

```powershell
java -jar build/libs/endpoint-enable-demo-1.0.0.jar --management.endpoint.info.enabled=true
```

Keep `management.endpoints.enabled-by-default=false` in the file.

Expected result:

| Observation | Value |
| --- | --- |
| Program stdout line | `INFO_ENDPOINT_BEAN_PRESENT=true` |
| `GET /actuator/info` | HTTP `200` |
| Global default in file | Still `false` |

This is evidence that the individual setting `info.enabled=true` is evaluated before the global default.

### 5.5. Experiment Comparison Table

| Run | Effective value of `info.enabled` | HTTP exposure list | `InfoEndpoint` bean present | HTTP `/actuator/info` |
| --- | --- | --- | --- | --- |
| A | `true` | `health,info` | Yes | `200` |
| B | `false` | `health,info` | No | `404` |
| C | `true` | `health,info` | Yes | `200` |

The table shows the expected results under the stated conditions. There are no Java changes across the three runs; what changes is the input configuration at startup.

## 6. The Value in the File May Not Be the Effective Value

Two types of precedence must be kept separate:

- **Configuration source precedence for the same key**: for example, the command-line value of `management.endpoint.info.enabled` overrides the value in `application.properties`.
- **Individual key precedence over global default**: after obtaining the values from the configuration environment, Actuator's mechanism checks the individual key before the global key.

For example, the file has:

```properties
management.endpoint.info.enabled=false
```

but the process is launched with:

```powershell
java -jar build/libs/endpoint-enable-demo-1.0.0.jar --management.endpoint.info.enabled=true
```

then the effective individual value is `true` under the example's standard startup. The corresponding environment variable is `MANAGEMENT_ENDPOINT_INFO_ENABLED`; profile-specific files can also alter the configuration that needs checking.

When diagnosing, inspect active profiles, environment variables, and startup arguments. Editing a file and re-reading that same file is not enough to prove the running process is using the new value. [Spring Boot 3.3 Configuration Source Order](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)

Endpoint enablement properties are evaluated during Spring context creation. For a typical Spring Boot application, editing the file after the process has started does not automatically create or remove endpoint beans; restart with the new configuration. This article does not assume any additional context-refresh mechanism.

## 7. Common Misconceptions

### 7.1. Adding to `include` and Assuming the Endpoint Is Enabled

The configuration:

```properties
management.endpoint.info.enabled=false
management.endpoints.web.exposure.include=health,info
```

still disables `info`. The exposure list does not override the enablement decision. If the goal is only to stop exposing it over HTTP, adjust HTTP exposure instead of using the general endpoint enable/disable property.

### 7.2. Setting `enabled=true` and Assuming Anyone Can Call It

Enablement configuration does not automatically grant access permission. An enabled endpoint may still be unexposed or blocked by security. When an application has Spring Security, results must be interpreted alongside the actual filter chain. [Securing Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security)

Do not change all security rules just to make an endpoint enable/disable experiment pass. The minimal example above intentionally uses only Web and Actuator to isolate and observe the behavior being studied.

### 7.3. Using `404` as the Sole Proof

In example B, the configuration, stdout line, and HTTP result all point to the endpoint being disabled. In another application, `404` can also result from the wrong port, wrong base path, an unexposed endpoint, or unmet auto-configuration conditions.

Similarly, `401` or `403` indicates the request hit a security mechanism; it is not enough by itself to conclude that the underlying endpoint is registered. A filter may handle the request before any endpoint mapping lookup occurs.

### 7.4. Disabling `health` and Forgetting the Health Check System

If the deployment platform calls a path belonging to the `health` endpoint, disabling this endpoint can leave health check requests unserved. When choosing default-disabled mode, explicitly enable the endpoints your operational platform relies on.

### 7.5. Changing the File Without Restarting or With Overriding Values Left Behind

Leaving an old process running, running the wrong JAR, or overlooking command-line arguments can all cause results to differ from predictions. In the lab, stop the process first and then start it again; verify the port and effective configuration before concluding the enable/disable mechanism is broken.

## 8. Self-check Through Controlled Changes

Use the sample project and perform each step in order, stopping the process before each next run:

1. Run the unmodified sample configuration, predict the presence of `InfoEndpoint`, and compare against stdout.
2. Run with `--management.endpoint.info.enabled=false`, keep exposure unchanged, and call the URL again.
3. Remove the line `management.endpoint.info.enabled=true` from the file, repackage, and run without override arguments. Explain why the global default `false` causes `info` to be disabled.
4. Re-enable `info` using the command-line argument `true`; explain why you do not need to change the global default.
5. In the sample project, change `management.endpoints.web.exposure.include` to `health` only while keeping `info.enabled=true`. Explain why looking at `enabled` alone is not enough to assert that the `/actuator/info` URL exists; auto-configuration also checks availability.

You have mastered this lesson when you can explain all three points: **where the enabled value comes from**, **why individual configuration wins over the global default**, and **why enabling an endpoint still requires checking exposure and access permissions**.
