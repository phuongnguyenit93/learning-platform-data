# Distinguishing 404 Errors Caused by Wrong Paths, Disabled Endpoints, or Unexposed Endpoints

## 1. One 404 Status Code, Three Different Questions

You call `GET /actuator/info` and get `404 Not Found`. Do not immediately conclude that the application is missing Actuator. Ask three questions:

1. **Is the address correct?** The request must reach the exact process, port, and path that the application is using.
2. **Is the endpoint enabled?** Configuration can disable a specific endpoint or disable endpoints by default and only re-enable selected ones.
3. **Is the endpoint exposed over HTTP?** An enabled endpoint does not necessarily have an HTTP path.

In this lesson, an **endpoint ID** is an identifier such as `health`, `info`, or `metrics`; an **HTTP path** is the access address constructed from configuration, such as `/actuator/info`. The two are related, but they are not the same.

The examples use **Spring Boot 3.3.13, Java 21, and a Spring MVC application packaged as a JAR**. The properties and defaults below belong to the 3.3 branch; when using a different version, cross-check the documentation for that exact version.

One way to visualize this:

```text
HTTP Request
  -> right target and right path?
  -> is an endpoint operation mapped to HTTP?
  -> allowed to proceed by security layers?
  -> endpoint operation handles it and returns a result
```

This is a mental model for diagnosis, not the exact execution order of Spring Security filters. A security filter may handle the request before Spring MVC looks up a mapping.

**A 404 is only an observed symptom. To determine the cause, you need to combine the HTTP result with the effective configuration and evidence from the running process.**

## 2. Distinguishing "Enabled" from "Exposed"

In Spring Boot 3.3, most built-in endpoints are enabled by default; `shutdown` is an exception. By default, only `health` is exposed over HTTP. The main configuration keys are:

```properties
management.endpoint.info.enabled=true
management.endpoints.web.exposure.include=health,info
```

The first line controls whether `info` is enabled; the second selects which endpoints are exposed over HTTP. Adding `info` to the exposure list cannot fix the fact that `info` is disabled. `exposure.exclude` takes precedence over `exposure.include`. These are separate mechanisms described in the [Spring Boot 3.3 endpoints documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.enabling).

For a minimal application with no Spring Security, no custom filters, and default URLs:

| State of `info` | Called URL | Expected result | Direction to check |
| --- | --- | --- | --- |
| Enabled, exposed, correct URL | `/actuator/info` | 200 | Endpoint is accessible |
| Enabled, exposed, typo in URL | `/actuators/info` | 404 | Compare URL against path configuration |
| Disabled, even though in exposure list | `/actuator/info` | 404 | Check `enabled` |
| Enabled, not exposed over HTTP | `/actuator/info` | 404 | Check the exposure list |
| Enabled, both included and excluded | `/actuator/info` | 404 | Check `exclude` |

The table describes the lab scenarios that will be reproduced below; it is not a rule for inferring backward from HTTP status codes across every system.

For auto-configured Spring Boot endpoints, bean creation conditions can also consider endpoint availability. Therefore, **not seeing a bean is not enough to distinguish "disabled" from "not exposed via any matching mechanism"**. You need to read why the auto-configuration condition did not match. This mechanism is implemented in [OnAvailableEndpointCondition in version 3.3.13](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/endpoint/condition/OnAvailableEndpointCondition.java).

## 3. First Branch: Calling the Wrong Address or Path

### 3.1. Compute the URL from Configuration, Do Not Guess from Habit

With the default configuration:

```text
http://localhost:8080/actuator/info
```

Break the URL into scheme, host, port, context path, Actuator base prefix, and endpoint path. Getting even a single component wrong can cause you to call the wrong resource.

A Servlet application sharing the same port:

```yaml
server:
  port: 8181
  servlet:
    context-path: /shop

management:
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,info
      path-mapping:
        info: details
```

The URL of `info` is now:

```text
http://localhost:8181/shop/manage/details
```

`/actuator/info`, `/manage/info`, or `/shop/manage/info` are not the configured address. Even though the path changed to `details`, the endpoint ID is still `info`: the exposure list still uses `info`, and the enable/disable key is still `management.endpoint.info.enabled`.

When separating the management port:

```yaml
server:
  port: 8181
  servlet:
    context-path: /shop

management:
  server:
    port: 8182
    base-path: /ops
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,info
```

In the JAR-packaged Servlet application of this lesson, the management address is:

```text
http://localhost:8182/ops/manage/info
```

Do not prepend `/shop` from the main application server onto this separate management path. If you call port 8181, you are calling the application server.

The official rule: when sharing the same port, the Actuator base path is relative to `server.servlet.context-path` for Servlet, or `spring.webflux.base-path` for WebFlux; when using a separate management port, it is relative to `management.server.base-path`. See [configuring the management server path and port](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html#actuator.monitoring.customizing-management-server-context-path).

### 3.2. Distinguishing a Wrong Port from a Connection Failure

Calling a port with no listening service usually results in a connection error, not an HTTP 404 response. If another service is running on that port, that service itself may return 404.

Therefore, "receiving an HTTP response" does not prove you reached the right application. Check the listening port, startup logs, deployed version, and proxy forwarding routes.

If the internal direct URL works but the public URL returns 404, compare how the proxy preserves or strips path prefixes. This is an isolation test: there is no need to change endpoint state when the error only appears behind a proxy.

Do not assume every project accepts a trailing `/` or automatically redirects misspelled paths. Use the exact configured URL first.

## 4. Second Branch: Endpoint Disabled

Example:

```yaml
management:
  endpoint:
    info:
      enabled: false
  endpoints:
    web:
      exposure:
        include: health,info
```

You added `info` to the exposure list, yet disabled that very endpoint. The fix when you actually need to use `info` is to change its enabled state; editing only the exposure list will not resolve the root cause.

It can also be configured to enable only selected endpoints:

```yaml
management:
  endpoints:
    enabled-by-default: false
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      enabled: true
```

Here `health` is re-enabled; `info` is not re-enabled. Do not look only for a line saying `info.enabled=false`: the disabled state can come from a global default policy.

The YAML snippets in sections 3–5 are **alternative configurations for analyzing each case**, not meant to be combined into a single file with duplicate `management` keys.

### Checking Effective Configuration

A file in source code is only one configuration source. Profiles, files outside the JAR, environment variables, JVM properties, and command-line arguments can all change the final value.

For example, in Spring Boot's default startup flow:

```shell
java -jar target/actuator-404-lab-1.0.0.jar --management.endpoint.info.enabled=false
```

Command-line arguments can override values in a file. Inspect both the startup command and deployment configuration instead of reading only `application.yml`. Precedence order is described in [Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

After changing configuration for an experiment, stop the old process and restart it. Do not assume editing YAML on disk will automatically recreate endpoints in an already running JAR process.

## 5. Third Branch: Endpoint Not Exposed over HTTP

Example:

```yaml
management:
  endpoint:
    info:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health
```

`info` is enabled, but the HTTP exposure list only selects `health`. What needs to be checked is the **web** exposure list, not the JMX list.

If configured as follows, `info` is still excluded from HTTP:

```yaml
management:
  endpoint:
    info:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,info
        exclude: info
```

When access to `info` is needed, the exclusion rule must also be addressed. Do not keep adding the endpoint name to `include` while ignoring `exclude`.

A name in `management.endpoints.jmx.exposure.include` does not create a corresponding HTTP URL. JMX and web are two separate exposure channels.

**Do not use `include: "*"` as a default fix for every 404.** In a situation where `info` is needed, expose exactly `health,info`; opening unrelated endpoints both makes the test harder to interpret and can leak additional operational information.

## 6. Runnable Lab: Changing One Condition to Find the Cause

### 6.1. Creating a Minimal Application

Prepare JDK 21, Maven 3.6.3 or later, and connectivity to Maven Central for the first dependency download; tool versions match the [Spring Boot 3.3 system requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html). The lab omits Spring Security, databases, proxies, or custom endpoints to minimize confounding factors.

File tree:

```text
actuator-404-lab/
├── pom.xml
└── src/main/java/example/Actuator404Application.java
```

Full contents of `pom.xml`:

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

    <groupId>example</groupId>
    <artifactId>actuator-404-lab</artifactId>
    <version>1.0.0</version>

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
            <artifactId>spring-boot-starter-actuator</artifactId>
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

Full contents of `src/main/java/example/Actuator404Application.java`:

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Actuator404Application {
    public static void main(String[] args) {
        SpringApplication.run(Actuator404Application.class, args);
    }
}
```

`@SpringBootApplication` activates application configuration; the two starters provide the HTTP server and Actuator infrastructure. There is no need to write a custom controller for `info`.

Compile and package from the directory containing `pom.xml`:

```shell
mvn clean package
```

This is an application with Spring dependencies, so use Maven to prepare the classpath and package it rather than running `javac Actuator404Application.java` alone.

Each scenario below uses two terminal windows: the first runs the application; the second sends requests. Wait for the application to start successfully. **Stop the process with Ctrl+C before running the next scenario.** Ports 8181 and 8182 must not already be in use.

The commands use the `curl` program. On Windows PowerShell, you can use `curl.exe` instead of `curl` to avoid PowerShell's alias. The `-o /dev/null` option below is for Bash on Linux/macOS; if using Windows, replace `/dev/null` with `NUL`. The `-w "%{http_code}\n"` option prints only the HTTP status code and a newline.

### 6.2. Control Baseline: Correct Path and Ready Endpoint

Start the application:

```shell
java -jar target/actuator-404-lab-1.0.0.jar --server.port=8181 --management.endpoint.info.enabled=true --management.endpoints.web.exposure.include=health,info
```

Send requests in sequence:

```shell
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8181/actuator/health
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8181/actuator/info
```

Stdout of the two curl commands:

```text
200
200
```

In this minimal application, `info` has no additional contributors, so the JSON body may be `{}`; that does not mean the endpoint is broken.

Keep the same process running and try misspelling the prefix:

```shell
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8181/actuators/info
```

Stdout:

```text
404
```

**Distinguishing evidence:** changing only the URL switches the response from 404 to 200 within the same process. No change to `enabled` or `exposure` is needed.

### 6.3. Disabling the Endpoint While Keeping Exposure Unchanged

Stop the process and run:

```shell
java -jar target/actuator-404-lab-1.0.0.jar --server.port=8181 --management.endpoint.info.enabled=false --management.endpoints.web.exposure.include=health,info
```

Call:

```shell
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8181/actuator/health
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8181/actuator/info
```

Stdout:

```text
200
404
```

Compared to the baseline, the URL and exposure list are unchanged; only the enabled state of `info` changed. This is the experimental evidence for the cause **endpoint disabled**.

### 6.4. Enabling the Endpoint, Removing It from the HTTP Exposure List

Stop the process and run:

```shell
java -jar target/actuator-404-lab-1.0.0.jar --server.port=8181 --management.endpoint.info.enabled=true --management.endpoints.web.exposure.include=health
```

Call the two URLs from section 6.3 again. Stdout:

```text
200
404
```

This time `enabled=true`, but `include` does not contain `info`. The HTTP result looks identical to section 6.3; configuration and controlled testing reveal the different cause.

You can verify exclusion precedence with a separate run:

```shell
java -jar target/actuator-404-lab-1.0.0.jar --server.port=8181 --management.endpoint.info.enabled=true --management.endpoints.web.exposure.include=health,info --management.endpoints.web.exposure.exclude=info
```

Call both URLs again: you still get 200 and 404 respectively. Removing the `exclude=info` rule and restarting with the control baseline restores `info`.

### 6.5. Changing the Path While Keeping the Endpoint ID Unchanged

Stop the process and run:

```shell
java -jar target/actuator-404-lab-1.0.0.jar --server.port=8181 --server.servlet.context-path=/shop --management.endpoints.web.base-path=/manage --management.endpoints.web.path-mapping.info=details --management.endpoint.info.enabled=true --management.endpoints.web.exposure.include=health,info
```

Call:

```shell
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8181/actuator/info
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8181/shop/manage/details
```

Stdout:

```text
404
200
```

The state of `info` is still correct. Editing the exposure list will not fix the old URL.

### 6.6. Verifying a Separate Management Port

Stop the process and run:

```shell
java -jar target/actuator-404-lab-1.0.0.jar --server.port=8181 --server.servlet.context-path=/shop --management.server.port=8182 --management.server.base-path=/ops --management.endpoints.web.base-path=/manage --management.endpoint.info.enabled=true --management.endpoints.web.exposure.include=health,info
```

Call:

```shell
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8181/shop/manage/info
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8182/ops/manage/info
```

Stdout:

```text
404
200
```

The application port still has a server responding, so the first request gets 404. The second request reaches the right management port and path.

## 7. Symptoms That Easily Lead to Wrong Conclusions

### 7.1. `/actuator` Returning 404 Does Not Prove Every Endpoint Is Gone

The Actuator root page is a discovery links page, not all child endpoints themselves. To observe the difference, run a separate instance:

```shell
java -jar target/actuator-404-lab-1.0.0.jar --server.port=8181 --management.endpoint.info.enabled=true --management.endpoints.web.exposure.include=health,info --management.endpoints.web.discovery.enabled=false
```

Call:

```shell
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8181/actuator
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8181/actuator/info
```

Stdout:

```text
404
200
```

Therefore, test the specific endpoint you are diagnosing directly. Nor is the links page a guaranteed inventory that every sub-resource exists. You can cross-check the discovery flag and path mapping in [WebEndpointProperties of Spring Boot 3.3.13](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/endpoint/web/WebEndpointProperties.java).

### 7.2. A 404 on a Sub-Resource Differs from Losing the Root Endpoint

For example, a call to `/actuator/metrics` returns the list of metric names successfully, yet a misspelled metric name at `/actuator/metrics/{name}` can return 404. In that case, do not rush to expose more endpoints: first check whether the metric name is in the list.

The structure of these two requests is described in the [metrics API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html). For read operations that return no data, the endpoint handler mapping layer can also return 404; see the [Actuator HTTP handler code](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/endpoint/web/servlet/AbstractWebMvcEndpointHandlerMapping.java). A 404 due to missing data does not mean the entire endpoint lacks a mapping.

### 7.3. Security Status Codes Are Not Definitive Proof of Mapping

In real applications, 401, 403, or a login redirect should lead you to check authentication and authorization. However, a filter can block even non-existent URLs; receiving 401 does not prove the endpoint is exposed. A custom security layer or gateway can also intentionally return 404.

The labs above omit Spring Security from dependencies to avoid mixing in this factor. When returning to a real application, use valid credentials and inspect the existing rules. Do not switch to `permitAll()` to try fixing a missing mapping.

### 7.4. A Valid Endpoint Name Does Not Guarantee Endpoint Creation Conditions Are Met

If the URL, enabled state, and exposure are all correct, check dependencies and auto-configuration conditions. For instance, `prometheus` requires the appropriate registry library; merely listing its name in the exposure list does not install the library.

This is an extension branch after ruling out the three main causes, not a reason to modify every configuration at once.

## 8. Diagnostic Procedure on a Running Application

1. **Record the original request:** method, full URL, HTTP status, body, and timestamp. Use `curl -i` when you also need headers; do not just screenshot a browser message line.
2. **Verify the responding target:** right application, deployed version, and port; if there is a proxy, compare against an allowed internal access point.
3. **Compute the actual URL:** check management port, context path, base path, and `path-mapping`. Test the child endpoint directly, not only the root page.
4. **Check enabled status:** both the per-endpoint key `management.endpoint.<id>.enabled` and `management.endpoints.enabled-by-default`.
5. **Check HTTP exposure:** `web.exposure.include` and `web.exposure.exclude`. Do not use JMX configuration to infer web paths.
6. **Cross-check effective configuration:** active profiles, environment variables, external files outside the JAR, and the startup command. Identify overridden values before editing.
7. **Gather more evidence when contradictions remain:** check startup logs and the auto-configuration conditions report with a diagnostic `--debug` run. Distinguish condition mismatches caused by being disabled, not exposed, or missing dependencies. You do not need to expose `env`, `beans`, or `conditions` to the Internet to read this evidence.
8. **Change exactly one identified cause:** update the URL, enable the needed endpoint, or adjust the exposure list; restart when required and repeat the exact same request.

Example using logs for local diagnosis:

```shell
java -jar target/actuator-404-lab-1.0.0.jar --debug --server.port=8181 --management.endpoint.info.enabled=false --management.endpoints.web.exposure.include=health,info
```

Find the condition section related to `InfoEndpointAutoConfiguration`; use the condition mismatch reason together with the startup configuration to confirm the hypothesis. Do not merely count the number of exposed endpoints in one log line and conclude which specific endpoint is missing.

## 9. Self-Check on Distinguishing Root Causes

**Scenario A:** `/actuator/health` returns 200, `/actuator/info` returns 404. Do you know for sure that `info` is disabled?

Not yet. The result only confirms that `health` is reachable at that address. You still need to check `info`'s own enabled/disabled state, exposure, and mapping.

**Scenario B:** `info.enabled=true`, `include=health,info`, `exclude=info`. Why does calling the exact URL still return 404 in the minimal app?

`exclude` removes `info` from web exposure. Enabling the endpoint and listing it in `include` does not override the exclusion rule.

**Scenario C:** After changing the base prefix to `/manage`, you call the old URL and get 404. Do you need to re-enable the endpoint?

There is no evidence it needs re-enabling. First call the URL computed from the new configuration; if the new URL returns 200, the cause is the access address.

**Scenario D:** `/actuator` returns 404, but `/actuator/info` returns 200.

The child endpoint is accessible. Check the discovery configuration or links-page path instead of concluding that Actuator is disabled.

**Scenario E:** Configuration in source code is correct, yet the process still returns old results.

Check the right JAR/process, active profile, overriding configuration sources, and whether a restart occurred. Diagnosis must rely on the state of the process actually serving requests.

Key takeaway: **access address, endpoint enabled state, and HTTP exposure are three independent axes of inspection. A controlled test and effective configuration distinguish them; a 404 code alone cannot.**
