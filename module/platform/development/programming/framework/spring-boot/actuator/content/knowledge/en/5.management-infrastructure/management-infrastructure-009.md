# Distinguishing Disabling Management HTTP Communication From Disabling All Endpoints

## 1. What Needs to Be Disabled?

An application can serve business APIs while providing health checks or operational info via Spring Boot Actuator. When someone says "disable Actuator," you must identify the exact goal:

- **Stop accessing Actuator over HTTP:** management paths cannot be called, while the JMX channel may still be kept.
- **Do not expose endpoints on a channel:** choose the set of endpoints exposed over HTTP or JMX.
- **Disable an endpoint:** prevent that endpoint from participating in Actuator mechanisms, rather than only changing access channels.

For example, the requirement "the order API keeps running, there are no Actuator URLs, and admins still check health via JMX" differs from "do not use any Actuator endpoints at all." Picking the wrong configuration can remove needed diagnostic tools or leave an unintended management channel open.

This lesson uses **Spring Boot 3.3.x**, with this version's `enabled` mechanism. Examples restart the application after changing configuration; editing a YAML file does not automatically alter the server or rebuild endpoints in a running process.

## 2. Model: Endpoint, Access Channel, and Access Permission

| Component | Question It Answers | Example |
| --- | --- | --- |
| Actuator endpoint | Which management capability is provided? | `health`, `info` |
| Enabled/disabled state | Is the endpoint permitted to operate by config? | `management.endpoint.health.enabled` |
| Exposure | Which channels is the endpoint exposed on? | `management.endpoints.web.exposure.include` |
| Management HTTP infrastructure | Are Actuator endpoints served over HTTP? | `management.server.port` |
| Authentication, authorization | Does the caller have permission to use it? | Spring Security rules for HTTP |

One way to reason when checking an HTTP call path is:

```text
Endpoint is eligible to operate
  + enabled
  + exposed over web
  + management HTTP active and URL is right
  + request passes access control if present
  → endpoint operation can be called over HTTP
```

This is a condition-checking model, not a bean-creation order diagram.

**Enabled does not mean exposed; exposed does not mean everyone is allowed to call it.** In Spring Boot 3.3, built-in endpoints are enabled by default except `shutdown`; default HTTP/JMX exposure includes only `health`. Some endpoints also require additional libraries or beans. You cannot infer that all endpoints are reachable merely because the Actuator starter was added. [Spring Boot 3.3 endpoint documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

Also distinguish "did not change the enabled flag" from "bean is guaranteed to still exist." Auto-configuration of many endpoints checks both enabled status and exposure capability. When no suitable channel remains, an endpoint may not be auto-configured. Custom-declared beans must be checked according to their own registration conditions. [Endpoint creation conditions in Spring Boot 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/endpoint/condition/OnAvailableEndpointCondition.java).

## 3. Disabling Management HTTP Communication

### 3.1. Using management.server.port=-1

```yaml
server:
  port: 8080

management:
  server:
    port: -1
```

This configuration stops serving Actuator endpoints over HTTP. Business APIs on port 8080 can still operate normally.

It does not mean "server listens on a negative port," nor does it merely remove a separate management port and automatically move Actuator back to the application port. `-1` is the configuration value used to disable management HTTP. Do not use `server.port=-1` instead: `server.port` controls the main web server and affects business APIs too.

If `management.server.port=8081` was used previously, changing it to `-1` stops serving Actuator HTTP on 8081; it does not make `/actuator/health` reappear on 8080 either. Merely changing the port from 8081 back to 8080 still serves Actuator HTTP, rather than disabling it.

### 3.2. Using web.exposure.exclude to Avoid Exposing Endpoints Over HTTP

Another option:

```yaml
management:
  endpoints:
    web:
      exposure:
        exclude: "*"
```

This is a web exposure policy: it excludes all endpoints from the HTTP channel. It does not set `enabled=false` per endpoint, does not alter the JMX exposure set, and is not a directive to shut down the web server.

If a separate management port was configured, do not use `exclude: "*"` to conclude that port was closed. When the goal also includes stopping management HTTP infrastructure, choose `management.server.port=-1`.

Both approaches are described in Spring Boot documentation for stopping HTTP endpoint exposure. [Spring Boot 3.3 HTTP management configuration](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html#actuator.monitoring.disabling-http-endpoints).

In YAML, `"*"` must be quoted. The following example also **does not** allow `health` through:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health
        exclude: "*"
```

`exclude` takes precedence over `include`. To keep only `health`, remove the exclude-all rule and set the appropriate `include` list.

### 3.3. Keeping JMX While HTTP Is Disabled

```yaml
server:
  port: 8080

spring:
  jmx:
    enabled: true

management:
  server:
    port: -1
  endpoint:
    health:
      enabled: true
    info:
      enabled: true
  endpoints:
    jmx:
      exposure:
        include: health,info
```

In an application with the Actuator starter and matching auto-configuration conditions, `health` and `info` are exposed via JMX while management HTTP is disabled.

Spring Boot does not enable Spring's JMX support by default; therefore the example explicitly sets `spring.jmx.enabled=true`. The health MBean is typically named `org.springframework.boot:type=Endpoint,name=Health` if domain and naming are unchanged. You can attach JConsole to the local JVM to inspect it. This does not automatically configure a remote JMX port; remote access is a separate setup. [Management over JMX in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html).

The key verification point is **HTTP is unreachable while the health MBean remains present**. Testing a single URL is not enough to prove all management capabilities were disabled.

## 4. Disabling Endpoints

### 4.1. Turning Off One Endpoint Across Actuator Channels

```yaml
management:
  endpoint:
    health:
      enabled: false
```

When health is disabled, adding `health` to the web or JMX exposure list does not re-enable it. The exposure list only selects eligible endpoints and does not override the `enabled` flag.

Note the property names:

- `management.endpoint.<id>.enabled`: singular **endpoint**, configuring one ID.
- `management.endpoints.enabled-by-default`: plural **endpoints**, configuring the global default.

No wildcard rule is used here in the form `management.endpoint.*.enabled=false`.

### 4.2. Defaulting All Endpoints to Disabled

```yaml
management:
  endpoints:
    enabled-by-default: false
```

This is an **opt-in only** mechanism. For endpoints following Actuator configuration, any endpoint without its own setting takes the disabled default. However, the following remains a valid exception:

```yaml
management:
  endpoints:
    enabled-by-default: false
    web:
      exposure:
        include: health
  endpoint:
    health:
      enabled: true
```

The result is that health is enabled and selected for web exposure; other endpoints continue following the disabled default. Thus, seeing `enabled-by-default=false` alone is not enough to confirm all endpoints are actually off. Check the effective value of each `management.endpoint.<id>.enabled`, including environment-specific settings and startup arguments.

To disable all endpoints via this mechanism:

1. Set `management.endpoints.enabled-by-default=false`.
2. Remove or set to `false` any individual enablement settings currently in effect.
3. Also check custom-declared endpoints and their registration conditions; do not generalize that every app-created bean is removed.
4. Restart and verify the channels used previously.

Disabling endpoints is not synonymous with closing the main web port, removing business controllers, or terminating the JVM.

### 4.3. Hiding Both HTTP and JMX Is a Different Requirement

```yaml
management:
  endpoints:
    web:
      exposure:
        exclude: "*"
    jmx:
      exposure:
        exclude: "*"
```

These two policies do not expose endpoints over the respective channels. They express decisions about **access channels**, rather than changing endpoint enable/disable defaults. Do not rely on these property names to assert that all endpoint beans are still created; auto-configuration conditions can still cause them to be absent.

Similarly, `spring.jmx.enabled=false` is a decision about Spring's JMX support, not a command to disable Actuator HTTP and not a command to disable all JVM or third-party MBeans.

## 5. Experiment: One Application, Different Outcomes

### 5.1. Prepare a Minimal Application

Use JDK 21, Spring Boot **3.3.0**, Gradle Wrapper 8.5. This standalone experiment needs two dependencies:

```groovy
dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

This is the dependencies block of a project that already has the Java and Spring Boot 3.3.0 plugins, not the entire `build.gradle`. Do not add Spring Security, custom security configs, databases, or other app dependencies to the experiment; they can change the outcome.

File `src/main/java/example/ActuatorToggleApplication.java`:

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ActuatorToggleApplication {

    public static void main(String[] args) {
        SpringApplication.run(ActuatorToggleApplication.class, args);
    }

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
```

Use `src/main/resources/application.yml`:

```yaml
server:
  port: 8080

spring:
  jmx:
    enabled: true

management:
  endpoints:
    web:
      exposure:
        include: health,info
    jmx:
      exposure:
        include: health,info
```

Start with this baseline, without any endpoint-disabling flags added yet. In PowerShell, run at the project directory:

```powershell
.\gradlew.bat bootRun
```

In Bash, the corresponding command is `./gradlew bootRun`. This app requires Spring libraries, so use the project's build flow instead of calling `javac` directly without a classpath.

### 5.2. Verify the Initial State

Open another PowerShell terminal:

```powershell
curl.exe -s http://localhost:8080/ping
```

Response body:

```text
pong
```

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://localhost:8080/actuator/health
```

When the minimal app is healthy, result:

```text
200
```

The default health payload under those conditions is `{"status":"UP"}`. Do not treat HTTP 200 as a universal rule for all apps: additional health check components can report other states.

In JConsole, select the right JVM, open the MBeans tab, and locate `org.springframework.boot → Endpoint → Health`. You can invoke the `health` operation to observe the result. Display names can differ if MBean naming configuration was customized.

### 5.3. Test Each Variant Independently

Each time, add only the configuration of **one row** below to the baseline, restart, and test. Before the next variant, remove the previously added config. Dots in the table denote full property names.

| Variant Added to Baseline | GET /ping | GET /actuator/health on 8080 | Health MBean |
| --- | --- | --- | --- |
| Nothing added | 200, body `pong` | 200 if healthy | Present |
| `management.server.port=-1` | 200, body `pong` | 404 | Present |
| `management.endpoints.web.exposure.exclude=*` | 200, body `pong` | 404 | Present |
| `management.endpoints.enabled-by-default=false` | 200, body `pong` | 404 | Absent |
| Disabled by default, with `management.endpoint.health.enabled=true` | 200, body `pong` | 200 if healthy | Present |
| `management.endpoint.health.enabled=false` | 200, body `pong` | 404 | Absent |
| Exclude `*` from both web and JMX | 200, body `pong` | 404 | Absent |

These results apply to the minimal app using default paths, with no security filters or custom controllers mapped to `/actuator/health`. "Health MBean Absent" refers only to Actuator's health endpoint in the experiment, not that the JVM has no MBeans left.

When adding YAML, merge into existing `management`, `endpoints`, and `endpoint` branches; do not create duplicate root keys. If testing a `.properties` file, write `exclude=*`; if testing YAML, write `exclude: "*"`.

You can check the business API status code with:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://localhost:8080/ping
```

For every variant in the table, the result remains:

```text
200
```

The table shows that the same HTTP 404 on health can stem from multiple causes. Only JMX presence and enable/disable configuration distinguish them.

## 6. Common Operational Misconceptions

### Seeing 404 and Concluding the Endpoint Is Disabled

404 can be caused by an unexposed endpoint, disabled management HTTP, wrong port, wrong URL prefix, or a disabled endpoint. Connection errors can also come from no listening server or network issues.

401/403 relate to access control; filters can respond even before a handler is matched. Thus, they also do not prove whether an endpoint is enabled or disabled. Check effective configuration, paths/ports, and JMX if present, rather than guessing from a single status code.

### Disabling the Discovery Page and Assuming All Endpoints Are Off

```yaml
management:
  endpoints:
    web:
      discovery:
        enabled: false
```

This configuration controls the discovery links page. In the baseline experiment, `/actuator/health` remains reachable. Disabling a listing page does not disable the operations that were listed.

### Disabling Endpoints and Assuming All Monitoring Data Stops

The `metrics` endpoint is one way to query metrics. Metrics collection and export via Micrometer also have separate configuration. Disabling endpoints or Actuator HTTP does not automatically disable all instrumentation, logging, tracing, or metric exporters. [Spring Boot 3.3 metrics configuration](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

Reasoning example: a push-based metrics system may not need the `/actuator/metrics` URL; conversely, a system pulling metrics from an HTTP endpoint loses that pull path when management HTTP is disabled.

### Forgetting Components That Call Health

If a load balancer or process-check mechanism calls health over HTTP, disabling that call path makes the check fail even while `/ping` still responds. Before changing configuration, identify who is calling, which URL/port is used, and any replacement mechanism.

Practical scenario: the requirement "keep only HTTP health for the load balancer" fits a minimal web exposure list. The requirement "allow only admins attaching JConsole locally, no Actuator HTTP" fits disabling management HTTP while intentionally keeping JMX.

## 7. Self-Check on Choosing Configuration

**Scenario 1:** Business APIs must stay active; admins still need JMX; no Actuator HTTP.

Choose `management.server.port=-1`, while enabling JMX and explicitly exposing the endpoints to keep. Do not default-disable all endpoints if you still want to use them over JMX.

**Scenario 2:** Keep HTTP health while not using the remaining endpoints.

Set `management.endpoints.enabled-by-default=false`, explicitly enable `management.endpoint.health.enabled=true`, and include `health` in web exposure. Verify no individual enablements remain for other endpoints.

**Scenario 3:** Set `enabled-by-default=false` yet health can still be called.

Look for an effective `management.endpoint.health.enabled=true`, including startup arguments or environment-specific config. If the endpoint is still eligible and exposed, an explicit per-endpoint override is expected behavior.

**Scenario 4:** Set `web.exposure.exclude="*"` yet JConsole still shows Health.

This is the expected result when JMX is enabled and health remains exposed over JMX. To change JMX, use JMX config; to disable health itself, use the endpoint's enabled flag.

When describing a change to teammates, state clearly: **which channel is turned off, which endpoints remain enabled, who is consuming them, and how it was verified**. That wording lets recipients know accurately what will continue operating.
