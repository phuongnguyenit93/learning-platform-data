# Configuring Include and Exclude Lists for JMX

An Actuator endpoint can be exposed over multiple management channels. With **JMX (Java Management Extensions)**, an endpoint is presented as an **MBean**, i.e., a management object registered in an `MBeanServer`. JMX tools or programs locate this object by its management name, rather than calling an HTTP URL.

This article explains how to choose endpoints exposed over JMX using two properties:

- `management.endpoints.jmx.exposure.include`: list of endpoint IDs selected for exposure.
- `management.endpoints.jmx.exposure.exclude`: list of endpoint IDs excluded from the JMX channel.

The scope is **Spring Boot 3.3.x**. The hands-on example uses **Spring Boot 3.3.13, Java 21, and Gradle 8.5**, with Spring Boot's default JMX auto-configuration mechanism.

## 1. Understanding the Relationship Between Endpoints, JMX, and MBeans

Imagine an application with three management capabilities: `health`, `info`, and `metrics`. You want operators to view health and application info over JMX, without exposing the metrics-reading endpoint on that channel.

The selection configuration is:

```properties
spring.jmx.enabled=true
management.endpoints.jmx.exposure.include=health,info,metrics
management.endpoints.jmx.exposure.exclude=metrics
```

If the conditions for creating the endpoints are met, the set exposed over JMX is `health` and `info`. `metrics` is selected in `include` and then removed by `exclude`.

Three decisions must be distinguished:

| Decision | Related configuration | Question answered |
| --- | --- | --- |
| Enable Spring's JMX support | `spring.jmx.enabled` | Does Spring auto-configure the MBean export mechanism? |
| Enable an Actuator endpoint | `management.endpoint.<id>.enabled` | Is that endpoint allowed to be active? |
| Expose endpoints over JMX | `management.endpoints.jmx.exposure.include/exclude` | Which endpoints are exported over the JMX channel? |

Other conditions such as dependent libraries and required beans must still be satisfied. An exposure list does not create an endpoint that does not exist.

### 1.1. Two Default Values That Are Easily Confused

In Spring Boot 3.3:

- `spring.jmx.enabled` defaults to `false`.
- `management.endpoints.jmx.exposure.include` defaults to `health`; `exclude` has no default excluded IDs.

Therefore, "JMX selects `health` by default" does not mean an application without JMX enabled automatically exports that endpoint. Those are default values of two different settings. [Spring Boot 3.3 Configuration Properties Appendix](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html)

## 2. Writing Lists with Proper Syntax

### 2.1. Properties Format

```properties
spring.jmx.enabled=true

management.endpoints.jmx.exposure.include=health,info,metrics
management.endpoints.jmx.exposure.exclude=metrics
```

Each element is an **endpoint ID**, such as `health`, not:

- A URL like `/actuator/health`.
- A class name like `HealthEndpoint`.
- An MBean name like `org.springframework.boot:type=Endpoint,name=Health`.

Configuration for the set of endpoints uses the plural branch `management.endpoints`. The key `management.endpoint.health.enabled` uses singular because it configures a single endpoint.

### 2.2. Equivalent YAML Format

```yaml
spring:
  jmx:
    enabled: true

management:
  endpoints:
    jmx:
      exposure:
        include:
          - health
          - info
          - metrics
        exclude:
          - metrics
```

A YAML list clarifies each item when there are many endpoints. It can also be written as a comma-separated string:

```yaml
management:
  endpoints:
    jmx:
      exposure:
        include: "health,info,metrics"
        exclude: "metrics"
```

The short block above only illustrates how to write the lists; `spring.jmx.enabled=true` is still required in the effective configuration.

### 2.3. A Custom List Replaces the Default Selection

If you set:

```properties
management.endpoints.jmx.exposure.include=info
```

then the selected list is `info`. Do not assume `health` is automatically added just because it is the default when unconfigured.

If you want both, write explicitly:

```properties
management.endpoints.jmx.exposure.include=health,info
```

This list does not represent execution order or a mandatory display order in JMX tools. The lab will explicitly sort names before printing to produce deterministic output.

## 3. Selection Rule: Include First, Exclude Wins on Overlap

You can use the following set model to reason about it:

```text
Endpoints eligible for JMX exposure
        → keep IDs selected by include
        → remove IDs present in exclude
        → register MBeans for the remaining endpoints
```

This is a model for explaining the outcome, not a detailed description of the order of all internal methods.

Suppose `health`, `info`, and `metrics` are all enabled, support JMX, and satisfy dependencies:

| include | exclude | Result among the three endpoints considered |
| --- | --- | --- |
| `health,info` | Unset | `health,info` |
| `health,info` | `info` | `health` |
| `info` | Unset | `info` |
| `health` | `metrics` | `health` |
| `*` | `info` | `health,metrics` |
| `health,info` | `*` | No endpoints |

An ID appearing in `exclude` cannot be "rescued" by adding that ID again to `include`. This rule is precedence between the two lists and does not depend on which line comes later in the file. [Spring Boot 3.3 Endpoint Exposure Rules](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)

### 3.1. Asterisk Selects All

JMX configuration example:

```yaml
spring:
  jmx:
    enabled: true

management:
  endpoints:
    jmx:
      exposure:
        include: "*"
        exclude:
          - env
          - beans
```

The asterisk must be quoted in YAML. If `*` is left unquoted, the YAML parser may treat it as alias reference syntax rather than a select-all string.

"All" here means all eligible endpoints on the JMX channel. It does not enable a disabled endpoint, replace missing libraries, or turn an HTTP-only endpoint into a JMX endpoint.

When a fixed set is required, listing each ID explicitly makes what will be exposed immediately visible. With `include="*"`, a newly eligible endpoint after adding a dependency may also enter the selected set.

### 3.2. Excluding All Endpoints from JMX

```properties
management.endpoints.jmx.exposure.exclude=*
```

This line excludes Actuator endpoints from the JMX channel, even if they appear in `include`. It does not mean disabling all MBeans in the JVM, nor does it automatically disable Actuator exposure over HTTP. [How to Stop Exposing JMX Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html)

## 4. JMX and HTTP Have Separate Exposure Lists

Example:

```properties
spring.jmx.enabled=true

management.endpoint.health.enabled=true
management.endpoint.info.enabled=true

management.endpoints.jmx.exposure.include=health,info
management.endpoints.web.exposure.include=health
```

Under matching conditions:

| Endpoint | JMX | HTTP |
| --- | --- | --- |
| `health` | Selected | Selected |
| `info` | Selected | Not selected |

If you add `management.endpoints.jmx.exposure.exclude=info`, only the JMX selection of `info` changes. If you set `management.endpoint.info.enabled=false`, the endpoint's enablement decision changes and that endpoint is not exposed over either channel.

A URL not appearing in HTTP does not prove the corresponding MBean is also absent. To check the JMX channel, inspect the right `MBeanServer` and the domain in use.

### 4.1. Domain Helps Locate the Right MBean

The default name of the `health` endpoint has the form:

```text
org.springframework.boot:type=Endpoint,name=Health
```

You can change the domain of Actuator endpoints:

```properties
management.endpoints.jmx.domain=learning.actuator
```

Then the corresponding name in the standard case is:

```text
learning.actuator:type=Endpoint,name=Health
```

Changing the domain does not change the endpoint ID in the lists: still use `health`. If an application has multiple Spring contexts and encounters name collisions, `spring.jmx.unique-names=true` is a related setting to check. [MBean Names and JMX Domain](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html)

## 5. Complete Hands-on: Printing the Registered MBean List

We will fix the domain `learning.actuator`, query MBeans with `type=Endpoint`, extract the `name` key property, and sort before printing. This check runs inside the application process itself without needing to open a remote JMX port.

The sample project has only Web and Actuator, without adding Spring Security, custom exporters, or multiple Spring contexts. The Web starter keeps the application running and allows verifying that JMX changes do not automatically change HTTP. The outputs below are **expected results with this exact sample project**.

### 5.1. Required Files

```text
jmx-exposure-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/JmxExposureApplication.java
    └── resources/application.properties
```

File `settings.gradle`:

```groovy
rootProject.name = 'jmx-exposure-demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

File `src/main/java/example/JmxExposureApplication.java`:

```java
package example;

import java.util.Set;
import java.util.stream.Collectors;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class JmxExposureApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmxExposureApplication.class, args);
    }

    @Bean
    ApplicationRunner inspectActuatorMBeans(ObjectProvider<MBeanServer> servers) {
        return args -> {
            MBeanServer server = servers.getIfAvailable();
            if (server == null) {
                System.out.println("ACTUATOR_MBEANS=<none>");
                return;
            }

            ObjectName pattern = new ObjectName(
                    "learning.actuator:type=Endpoint,*");
            Set<ObjectName> names = server.queryNames(pattern, null);

            String result = names.stream()
                    .map(name -> name.getKeyProperty("name"))
                    .sorted()
                    .collect(Collectors.joining(","));

            System.out.println("ACTUATOR_MBEANS="
                    + (result.isEmpty() ? "<none>" : result));
        };
    }
}
```

`MBeanServer.queryNames` returns the set of names matching the query pattern. The pattern `learning.actuator:type=Endpoint,*` restricts the domain and MBean type while allowing additional key properties. The code uses `sorted()` because the result set does not guarantee the desired print order. [Java 21 MBean Query API](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html#queryNames(javax.management.ObjectName,javax.management.QueryExp))

`ObjectProvider` allows the program to still start when the sample configuration provides no `MBeanServer` bean. In this program, `<none>` means there are no matching endpoint names to report, or there is no server bean to query. It does not mean there are no MBeans left in the entire JVM.

File `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8087

spring.jmx.enabled=true
management.endpoints.jmx.domain=learning.actuator

management.endpoints.enabled-by-default=false
management.endpoint.health.enabled=true
management.endpoint.info.enabled=true
management.endpoint.metrics.enabled=true

management.endpoints.jmx.exposure.include=health,info,metrics
management.endpoints.jmx.exposure.exclude=metrics
management.endpoints.web.exposure.include=health
```

The global default is set to disabled and only the three endpoints under study are explicitly enabled. Thus the example does not depend on whether other endpoints are enabled or disabled by default. The HTTP list contains only `health`.

### 5.2. Compiling and Running Case A

JDK 21, Gradle 8.5, and an internet connection for first-time dependency downloads are required. In the project directory:

```powershell
gradle bootJar
java -jar build/libs/jmx-exposure-demo-1.0.0.jar
```

If the project already has Gradle Wrapper 8.5, replace the first command with `.\gradlew.bat bootJar`. The code depends on Spring, so use Gradle to compile and package rather than invoking `javac` alone.

In stdout during startup, the line printed by the sample program is:

```text
ACTUATOR_MBEANS=Health,Info
```

Reason:

- All three endpoints were explicitly enabled.
- `include` selects all three IDs.
- `exclude` removes `metrics`.
- The program extracts the MBean's `name` property and sorts it, so it prints `Health,Info`.

Distinguish the capitalization in the output from the configuration IDs: the lists are still written `health,info`, not changed to `Health,Info`.

### 5.3. Case B: Proving Exclude Takes Precedence

Stop case A with `Ctrl+C`, then run the same JAR again:

```powershell
java -jar build/libs/jmx-exposure-demo-1.0.0.jar --management.endpoints.jmx.exposure.exclude=info
```

The command-line argument replaces this run's `exclude` list value with `info` only; it does not append `info` to the `metrics` value in the file.

Expected output:

```text
ACTUATOR_MBEANS=Health,Metrics
```

`info` is still present in `include` but is excluded. `metrics` is no longer in the effective exclude list, so it is exposed.

### 5.4. Case C: Include List Replaces the Default or Previous List

Stop case B and run:

```powershell
java -jar build/libs/jmx-exposure-demo-1.0.0.jar --management.endpoints.jmx.exposure.include=info
```

The new run does not inherit command-line arguments from run B. `exclude=metrics` in the file takes effect again; `include` for this run is only `info`.

Expected output:

```text
ACTUATOR_MBEANS=Info
```

There is no `Health` in the result line because `health` is not in the effective JMX list. That does not disable the `health` endpoint on HTTP.

In a second PowerShell window:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/actuator/health
```

With the sample application healthy, expected output is:

```text
200
```

This comparison shows the two channels have independent exposure selections. Actual health status can still affect the HTTP code, so do not generalize `200` to every environment.

### 5.5. Case D: Excluding Everything from JMX

Stop case C and run:

```powershell
java -jar build/libs/jmx-exposure-demo-1.0.0.jar "--management.endpoints.jmx.exposure.exclude=*"
```

Expected output:

```text
ACTUATOR_MBEANS=<none>
```

Here `spring.jmx.enabled` is still `true`. The empty result is due to the selector excluding all Actuator endpoints from JMX. Calling `/actuator/health` again is still served over HTTP under the sample conditions.

### 5.6. Case E: Include Does Not Re-enable a Disabled Endpoint

Stop case D and run:

```powershell
java -jar build/libs/jmx-exposure-demo-1.0.0.jar --management.endpoint.info.enabled=false
```

This run uses the lists in the file again: selects `health,info,metrics`, excludes `metrics`. However, `info` is disabled at the endpoint level.

Expected output:

```text
ACTUATOR_MBEANS=Health
```

`include` does not override `enabled=false`.

### 5.7. Case F: Disabling Spring's JMX Mechanism

Stop case E and run:

```powershell
java -jar build/libs/jmx-exposure-demo-1.0.0.jar --spring.jmx.enabled=false
```

In the sample project without other server or exporter configurations, expected output is:

```text
ACTUATOR_MBEANS=<none>
```

Still having the IDs declared in `include` does not automatically re-enable JMX support.

### 5.8. Verification Table

Each row is a fresh startup using the sample file plus only that case's argument:

| Case | Change from sample file | Expected stdout line |
| --- | --- | --- |
| A | Unchanged | `ACTUATOR_MBEANS=Health,Info` |
| B | `exclude=info` | `ACTUATOR_MBEANS=Health,Metrics` |
| C | `include=info` | `ACTUATOR_MBEANS=Info` |
| D | `exclude=*` | `ACTUATOR_MBEANS=<none>` |
| E | `info.enabled=false` | `ACTUATOR_MBEANS=Health` |
| F | `spring.jmx.enabled=false` | `ACTUATOR_MBEANS=<none>` |

The names in the table are only the query results from the example's Actuator domain; they are not the list of all MBeans in the JVM.

## 6. Inspecting with JMX Tools and Understanding Exposure Limits

If JConsole is available in the JDK, you can open `jconsole`, connect to the local Java process of the sample project, and find the `learning.actuator` domain under MBeans. Select the right running process and ensure appropriate local access permissions; typically the tool and the application must run under the same OS user account.

After each application restart, reconnect to the right process. If the process cannot be found because the environment does not support attach, the query in `ApplicationRunner` remains the observation method for this lesson. [Local JMX Monitoring with Java 21](https://docs.oracle.com/en/java/javase/21/management/monitoring-and-management-using-jmx-technology.html)

Two boundaries must be understood clearly:

1. `spring.jmx.enabled=true` and the Actuator lists serve Spring's MBean registration/exposure. They do not fully configure a remote JMX connection; the JVM side has its own remote management settings.
2. `include` and `exclude` select endpoints, not a list of users permitted to invoke them. If using a remote JMX connection, authentication, authorization, and connection protection belong to the corresponding JMX configuration. HTTP rules in `SecurityFilterChain` do not automatically protect a separate JMX connection.

No remote management port needs to be opened to complete the experiments in this lesson.

## 7. Diagnosing When the Observed List Differs from Expectations

| Symptom | What to check |
| --- | --- |
| No Actuator MBeans visible at all | `spring.jmx.enabled`, query domain, connected process, and `exclude=*` |
| An included endpoint is missing | Whether it is excluded; whether the endpoint is enabled and has required libraries/beans |
| Still seeing `java.lang` MBeans after excluding all | That is a different domain; this list only controls Actuator endpoints over JMX |
| Endpoint is on HTTP but not on JMX | Compare the two independent exposure lists |
| `health` is missing after including only `info` | The effective list replaced the default selection |
| List in file looks right but result differs | Check active profiles, command-line arguments, and overriding config sources |
| Duplicate MBean name error | Check multiple contexts, domains, and unique-names configuration |

A property can be supplied from a file, environment variable, or command line. For example, the environment variable for the selection list is `MANAGEMENT_ENDPOINTS_JMX_EXPOSURE_INCLUDE`. With standard startup, `--management.endpoints.jmx.exposure.include=info` overrides the value of the same key in the file. You must inspect the **effective list**, not only the text in one file. [Configuration Sources and Precedence](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)

Editing a file in a typical Spring Boot application does not immediately refresh the registered MBean set. In these experiments, always stop the process and restart with the new configuration.

In addition, an endpoint excluded only from JMX may still be created to serve another channel. If it is not exposed on any suitable channel, auto-configuration conditions may also remain unmet. Therefore, do not conclude "the bean definitely still exists" or "the bean is definitely gone" from a JMX list alone.

## 8. Self-check Exercises

Use the sample project and predict before running:

1. Change `include` to `health,info` and `exclude` to `health`. Which names remain in the stdout line?
2. Set `include=*`, keep the global default disabled, and enable only the three sample endpoints. Why does the asterisk not create other endpoints?
3. Keep `include=health,info,metrics` but disable `info` and exclude `metrics`. Distinguish the two reasons why these two names are absent.
4. Set `exclude=*` for JMX and then check the `health` URL again. Explain why the two channels yield different results.
5. Change the Actuator domain to `study.actuator` without updating the Java query pattern. Why might the old query result be empty even though MBeans are registered in the new domain?

The short answer for question 1 is `Info`. For question 2, only enabled, JMX-compatible, and eligible endpoints can be selected. Question 3 has two separate causes: `info` is disabled at the endpoint level, while `metrics` is excluded from the JMX channel. Question 4 requires comparing the `web` and `jmx` lists. Question 5 requires updating the `ObjectName` domain or looking in the right domain in the management tool.
