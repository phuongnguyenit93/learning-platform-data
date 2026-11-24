# Finding Why an Endpoint Does Not Appear Even When Configured in include

## 1. Understanding What "Adding an Endpoint to include" Actually Means

Suppose you have configured:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
```

Yet `GET /actuator/prometheus` still returns 404. This does not necessarily mean Spring Boot is ignoring your YAML. **The include list selects which endpoints are exposed over a channel; it does not create endpoints, add libraries, re-enable disabled features, or grant access permissions.**

For an HTTP request to reach the right Actuator operation, multiple conditions must hold at the same time:

```text
Required code and dependencies exist
        ↓
Endpoint creation conditions are satisfied
        ↓
Endpoint is enabled by the corresponding configuration
        ↓
Endpoint is included for HTTP and not excluded
        ↓
Web infrastructure and matching operation mapping exist
        ↓
Request uses the right scheme, host, port, path, and method
        ↓
Security/proxy layers allow the request to reach the operation
```

This is a diagnostic model, not a claim that every endpoint is constructed in one fixed internal sequence. Auto-configuration conditions can evaluate several factors simultaneously.

In Spring Boot 3.3, distinguish **enabling an endpoint** (enablement) from **exposing an endpoint** (exposure). `exclude` takes precedence over `include` within the same exposure channel. See [Spring Boot 3.3 Actuator Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

This lesson uses the configuration mechanisms of Spring Boot 3.3.x. When looking things up, select the matching documentation version; do not copy a property from a newer version into a 3.3 application and assume it has the same effect.

## 2. Identifying Exactly What "Does Not Appear" Means

The following symptoms require different lines of investigation:

| Symptom | What to check first |
| --- | --- |
| Cannot connect, connection refused, or timeout | Process, listener, port, bind address, network, and proxy |
| Returns 404 | Actual URL, error origin, mapping, exposure, and endpoint creation conditions |
| Returns 401 | Authentication mechanism and credentials |
| Returns 403 | Access permissions, security policy, and CSRF if it is a state-changing operation |
| Returns 405 | Whether the HTTP method matches the operation |
| Returns 200 with `{}` | The endpoint may already exist but have no data to present yet |
| Missing link in `/actuator` | Discovery configuration and endpoints exposed at that address |
| Works with curl but web UI reports an error | CORS, mixed content, credentials, and the actual browser request sent |
| Not visible in Swagger/OpenAPI | How the documentation tool discovers mappings, not only Actuator configuration |

The status code is a clue, not standalone proof of the cause. A proxy or custom security filter may return 404 before the request reaches Actuator's mapping. Conversely, an unmapped URL can still be blocked earlier by a security layer with 401.

A `200 {}` response from `/actuator/info` does not mean the endpoint is missing. It is completely different from 404: the operation was invoked and returned an empty object. To populate build, Git, or other data sources, you need to configure the corresponding contributor.

Before changing configuration, record four facts: full URL, method, status code, and where the response actually originated. If calling through a gateway, compare with a direct call to the instance over an allowed management access route.

## 3. Starting with a Short Verification Checklist

Do not change dependencies, security, and every property at the same time. Follow verifiable questions:

1. **Are you running the right application, version, and instance?** Check the process or deployment metadata; avoid editing a newer build's file while calling an older one.
2. **Where is management HTTP located?** Identify scheme, port, context path, base path, and path mapping.
3. **What is the actual response?** Separate connection errors, 404, 401/403, 405, and empty 200.
4. **Is the effective configuration right?** Check profiles, overriding sources, include, exclude, and enablement.
5. **Are the endpoint's creation conditions met?** Check dependencies, required beans, and the auto-configuration conditions report.
6. **Does the mapping exist in the right channel?** Distinguish HTTP from JMX, and the discovery list from the actual endpoint.
7. **Is an intermediate layer blocking or rewriting the path?** Check security, proxy, ingress, and per-instance versions.
8. **Did you restart and test the right build after changing things?** Do not infer runtime application state from file contents on disk.

Each step should yield a concrete observation, such as "info is excluded by exclude in the production profile," rather than "Actuator seems broken."

## 4. Checking Effective Configuration, Not Just the File You Edited

### 4.1. Exact Property Names and YAML Structure

These three property groups are not interchangeable:

```properties
management.endpoints.web.exposure.include=health,info
management.endpoints.web.exposure.exclude=info
management.endpoint.info.enabled=true
```

- `endpoints.web.exposure` is plural because it configures the set of endpoints exposed over web.
- `endpoint.info.enabled` is singular because it configures the `info` endpoint specifically.
- `include` accepts IDs such as `info`, not URLs like `/actuator/info`.

With the example above, `info` is still excluded from HTTP because it appears in `exclude`. Setting `enabled=true` does not override the exclusion list.

Corresponding YAML form:

```yaml
management:
  endpoint:
    info:
      enabled: true
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
        exclude:
          - info
```

Do not fix indentation errors by creating multiple duplicate `management:` keys in the same YAML document. Combine them into one valid tree. If using a wildcard in YAML, you must quote it as `"*"`; however, exposing all endpoints is not a default diagnostic practice.

### 4.2. Profiles, Environment Variables, and Runtime Arguments Can Override

A file containing `include: health,info` does not prove the running process uses that list. Check these possibilities:

- The profile file you edited does not belong to the active profile.
- An external configuration file outside the JAR overrides the file packaged inside the JAR.
- An environment variable or command-line argument resets the list.
- `spring.config.name` or `spring.config.location` causes the application to read a different source.
- A container is running an older configuration or image.
- You edited the configuration, but the process has not been restarted.

Example argument:

```bash
java -jar endpoint-lab-1.0.0.jar --management.endpoints.web.exposure.include=health
```

Under normal Spring Boot startup, this argument has higher precedence than values in a file. Do not assume `info` is merged from a list in a lower-precedence source. See [Spring Boot 3.3 Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

Collect only the keys needed for diagnosis. Printing all environment variables or configuration can leak credentials into logs or incident tickets. If using `env` or `configprops`, use a protected access path; never publicly expose those endpoints just to inspect one value.

### 4.3. Per-Endpoint Enablement and Default Enablement Are Two Separate Layers

Example of intentional opt-in enablement:

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

Here, `health` is enabled individually; `info` is not enabled yet. Adding `info` to include alone is not enough. If you truly need to expose it, add:

```yaml
management:
  endpoint:
    info:
      enabled: true
```

This is an addition to the existing tree, not an instruction to create a second `management` key in the same document.

For auto-configured endpoints, availability conditions can check both enablement and exposure. The [ConditionalOnAvailableEndpoint](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/endpoint/condition/ConditionalOnAvailableEndpoint.html) API describes this check. Therefore, when a bean is not created, read the reason the condition was not met instead of merely looking for a Java class on the classpath.

## 5. Does the Endpoint Have Required Dependencies and Supporting Beans?

`include` is configuration, not a library installer. Having an ID in the list does not guarantee the corresponding endpoint exists.

| Endpoint/situation | Condition worth checking |
| --- | --- |
| No Actuator endpoints at all | Is `spring-boot-starter-actuator` on the runtime classpath of the actual running app? |
| `prometheus` does not appear | Is a matching Prometheus registry present and metrics export auto-configuration enabled? |
| `httpexchanges` does not appear | Is there an `HttpExchangeRepository` bean? |
| `logfile` does not appear | Does the app configure log output to a file properly? Console-only logging is not enough |
| `startup` does not appear | Is `BufferingApplicationStartup` used to supply startup data? |
| Custom endpoint does not appear | Did the endpoint class actually become a discovered Spring bean in the context? |

### Example with Prometheus

If the application only has the Actuator starter, the configuration:

```properties
management.endpoints.web.exposure.include=health,prometheus
```

does not automatically add `io.micrometer:micrometer-registry-prometheus`. When Prometheus export is needed, check that dependency in the runtime graph, the version managed by Spring Boot, and the properties controlling the exporter. Do not check only a dependency entry in another module or in test scope.

Spring Boot 3.3 Prometheus auto-configuration has conditions on the registry class, beans, and exporter state; see [PrometheusMetricsExportAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/metrics/export/prometheus/PrometheusMetricsExportAutoConfiguration.html).

The presence of `/actuator/metrics` does not prove `/actuator/prometheus` must exist. The two endpoints serve different purposes and have different supporting conditions.

With `httpexchanges`, missing a repository is different from "the repository exists but has not recorded any exchanges yet." The first relates to endpoint creation conditions; the second relates to data.

Do not mechanically add libraries or beans if the application does not need that capability. A valid diagnostic finding can be "this ID is included even though the application does not provide that endpoint"; in that case, fix expectations or remove redundant configuration.

## 6. HTTP and JMX Are Two Separate Exposure Channels

The following configuration selects endpoints only for JMX:

```yaml
management:
  endpoints:
    jmx:
      exposure:
        include: health,info
```

It is not equivalent to:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
```

Even when JMX is enabled and an endpoint is accessible via JMX, you cannot conclude `GET /actuator/info` has an HTTP mapping. Conversely, HTTP working does not prove the corresponding MBean is exposed.

If the application runs with `WebApplicationType.NONE` or lacks web infrastructure, adding `web.exposure.include` does not turn it into a web server. First verify whether the application is designed to serve HTTP. Do not change the application type just to make a management URL appear when the app has no need for it.

For custom endpoints, `@JmxEndpoint` is for JMX only; `@WebEndpoint` is for web. Do not use one channel's include list to explain an absence in the other channel.

## 7. Recomputing the Actual URL

### 7.1. When Sharing the Port with a Servlet Application

Suppose the configuration is:

```yaml
server:
  port: 18080
  servlet:
    context-path: /shop

management:
  endpoints:
    web:
      base-path: /manage
      path-mapping:
        info: about
      exposure:
        include: health,info
```

The corresponding URLs are:

```text
Health: http://localhost:18080/shop/manage/health
Info:   http://localhost:18080/shop/manage/about
```

Calling `http://localhost:18080/actuator/info` checks a different path. The endpoint can still be working properly at the new URL.

### 7.2. When Using a Separate Management Port

Servlet example:

```yaml
server:
  port: 18080
  servlet:
    context-path: /shop

management:
  server:
    port: 19090
    address: 127.0.0.1
    base-path: /ops
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,info
```

The info endpoint is located at:

```text
http://127.0.0.1:19090/ops/manage/info
```

Do not prepend `/shop` from the business port onto the separate management URL. When sharing a port, the web base path is relative to the Servlet context path or WebFlux base path; when using a separate management port, it is relative to `management.server.base-path`. See [Monitoring and Management Over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

Also check HTTP vs HTTPS, the bind address, and whether the port is forwarded by the container or proxy. `127.0.0.1` restricts access to the process's network namespace; inside a container, it is not automatically the loopback of the host running curl.

### 7.3. Management HTTP Can Be Disabled or Use a Random Port

- `management.server.port=-1`: disables serving management endpoints over HTTP.
- `management.server.port=0`: picks a random port according to the corresponding management mechanism; read the actual port from the process/logs instead of calling a fixed port number.
- No separate management port configured: normally uses the application's port.

The meaning of the management port is described in [ManagementServerProperties](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/web/server/ManagementServerProperties.html). Using a separate port can also create a separate management context; see [ManagementContextAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/web/server/ManagementContextAutoConfiguration.html).

In a multi-instance system, avoid reading logs from instance A and then calling a load-balanced URL that routes to instance B. An un-updated replica can make results alternate between 200 and 404.

## 8. Distinguishing Mapping from Access Permissions and HTTP Methods

An exposed endpoint does not mean everyone is allowed to call it. In a Servlet application with Spring Security, default rules and custom `SecurityFilterChain` beans can produce different behavior.

If no custom security chain is defined, Actuator security auto-configuration permits unauthenticated access to health and protects other endpoints under applicable conditions. When application-defined security chains exist, you must inspect those exact rules rather than continuing to rely on default assumptions. See [ManagementWebSecurityAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/ManagementWebSecurityAutoConfiguration.html).

A sensible verification sequence:

1. Record 401/403 and relevant headers, not only the error body.
2. Identify which security chain handles the actual management URL.
3. Check credentials, roles/authorities, and chain ordering.
4. If the URL changed port or base path, re-check the matchers.
5. If behind a proxy, check whether the proxy blocks, authenticates separately, or rewrites paths.

Do not set `permitAll` for all of Actuator or disable Spring Security just to turn an access error into "endpoint fixed."

The HTTP method must also match the operation. For endpoints using standard operation annotations:

| Operation | HTTP Method |
| --- | --- |
| `@ReadOperation` | GET |
| `@WriteOperation` | POST |
| `@DeleteOperation` | DELETE |

An endpoint that only has a write operation does not automatically provide a read operation for you to test by opening the URL in a browser. If you reach the right mapping with the wrong method, you may receive 405; earlier filter layers can still alter the outcome.

For state-changing operations, 403 may involve CSRF rather than a missing endpoint. Handle it according to the application's security model, without disabling CSRF system-wide just to test one management request. When diagnosing existence, prefer read operations and avoid test-calling operations with side effects such as shutdown.

If direct curl works while JavaScript on another website cannot read the response, check CORS and preflight requests. Exposure, authorization, and CORS are separate concerns; changing include does not solve all three.

## 9. Do Not Use Discovery or Docs UI as Standalone Proof

`/actuator` is typically the page containing HTTP endpoint discovery links. However:

```properties
management.endpoints.web.discovery.enabled=false
```

can disable the discovery page while a URL such as `/actuator/info` continues to work. When the web base path is set to `/`, the discovery page also has rules to avoid colliding with root mappings.

Therefore:

- Failing to open `/actuator` is not enough to conclude all endpoints have vanished.
- The HTTP links list is not a list of all JMX capabilities.
- Not seeing an endpoint in Swagger/OpenAPI is not enough to conclude no HTTP mapping exists.
- Empty endpoint data or hidden details also differs from an unmapped endpoint.

Call the properly computed operation URL directly with appropriate permissions. Use discovery and documentation tools as supporting evidence, never as a replacement for testing the actual operation.

## 10. Reading Auto-Configuration Evidence and Checking Custom Endpoints

### 10.1. When a Spring Boot-Provided Endpoint Is Not Created

In an environment where diagnosis is permitted, you can start with debug enabled to inspect the auto-configuration conditions report:

```bash
java -jar endpoint-lab-1.0.0.jar --debug
```

Find the configuration group related to the suspected endpoint or exporter, and read the reason the condition did not match. For instance, distinguish a missing registry class from a property disabling the exporter or endpoint.

Do not treat the presence of an auto-configuration class name in the JAR as proof that the bean exists. An auto-configuration class can be found yet not applied due to an unmet condition. Likewise, a log line saying "exposing N endpoints" is only a summary indicator; it does not explain which specific endpoint is missing or where a proxied URL is being blocked.

If `conditions`, `beans`, `mappings`, or context inspection tools are already provided over a protected management route, you can use them to cross-check. Do not create a circular dependency of "must expose the conditions endpoint before Actuator can be diagnosed": startup logs and the conditions report are equally valuable.

When sharing evidence, extract the relevant section, redact sensitive data, and preserve enough context to reproduce: Boot version, profile, URL, method, effective properties, and the unmet condition.

### 10.2. When an Application-Defined Custom Endpoint Is Not Discovered

Check from bean registration through to operations:

1. Has the endpoint class been registered via component scanning or `@Bean`?
2. Is that package within the scan scope of the running application?
3. Is there a `@Profile` or condition preventing bean creation?
4. Do the endpoint annotation and ID match the channel you intend to use?
5. Is there an appropriate operation such as `@ReadOperation` to generate a GET request handler?
6. Does `@Selector` cause the operation to require an extra path segment?
7. Is there an `EndpointFilter` or custom extension affecting exposure?

A class annotated with `@Endpoint` that does not become a bean cannot be "revived" merely by adding its ID to include. Conversely, a regular `@RestController` with `@GetMapping` belongs to the controller mapping mechanism; do not assume it is an Actuator endpoint governed by this list.

For custom endpoints, you must also inspect how the bean and its availability conditions are declared. Do not mechanically apply every assumption about built-in endpoint auto-configuration to a bean registered through a custom mechanism.

## 11. Lab: Same include, Different Outcomes

The following lab is a **standalone application** using Java 17 or later, Maven, and Spring Boot 3.3.0 to pin the example. It binds only to loopback and does not add Spring Security or a Prometheus registry. Run it in a fresh directory without profiles or external config sources altering the properties under test.

### 11.1. Creating the Minimal Program

Structure:

```text
endpoint-lab/
├── pom.xml
└── src/main/
    ├── java/lab/EndpointLabApplication.java
    └── resources/application.properties
```

Contents of `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>endpoint-lab</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
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

Contents of `src/main/java/lab/EndpointLabApplication.java`:

```java
package lab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EndpointLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(EndpointLabApplication.class, args);
    }
}
```

Contents of `src/main/resources/application.properties`:

```properties
spring.application.name=endpoint-lab
server.address=127.0.0.1
server.port=18080
management.endpoints.web.exposure.include=health,info
```

Package and run from the directory containing the POM:

```bash
mvn -q package
java -jar target/endpoint-lab-1.0.0.jar
```

Maven needs access to the dependency repository on the first download. If port 18080 is already in use, choose another port and update the test URLs accordingly. Startup logs contain timestamps, PID, and environment details, so startup stdout is not fixed.

In a second terminal, using Bash and curl:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18080/actuator/info
```

When the application starts successfully with the exact configuration above, expected stdout is:

```text
200
```

Read the body:

```bash
curl -s http://127.0.0.1:18080/actuator/info
```

The expected body is `{}` because the example provides no additional info data yet. This command is not guaranteed to print a trailing newline automatically. On PowerShell, use `curl.exe` to avoid hitting the alias; when fetching only the status code, you can replace `/dev/null` with `NUL`.

### 11.2. Reproducing Each Cause, One Change at a Time

Before each test, stop the previous process with Ctrl+C, keep the original config file unchanged, and run the exact command for that case. Do not accumulate arguments from previous tests.

**Case A — endpoint disabled despite being in include:**

```bash
java -jar target/endpoint-lab-1.0.0.jar --management.endpoint.info.enabled=false
```

The curl command above checking the status code of `/actuator/info` is expected to print `404`. The cause is that the info endpoint is disabled, not that include needs to be written again.

**Case B — exclude removes the endpoint:**

```bash
java -jar target/endpoint-lab-1.0.0.jar --management.endpoints.web.exposure.exclude=info
```

`/actuator/info` is expected to return 404. The exclude argument is not overridden by the include list in the file.

**Case C — ID declared, but supporting registry missing:**

```bash
java -jar target/endpoint-lab-1.0.0.jar --management.endpoints.web.exposure.include=health,info,prometheus
```

Check:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18080/actuator/info
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18080/actuator/prometheus
```

With the lab's exact dependencies, expected stdout in order is:

```text
200
404
```

This result illustrates that Actuator is running in the same process, yet include does not supply the Prometheus registry on its own.

**Case D — endpoint works at a changed URL:**

```bash
java -jar target/endpoint-lab-1.0.0.jar --server.servlet.context-path=/shop --management.endpoints.web.base-path=/manage --management.endpoints.web.path-mapping.info=about
```

Check the old path, then the new path:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18080/actuator/info
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18080/shop/manage/about
```

Expected stdout:

```text
404
200
```

The endpoint did not disappear; the URL used to test it was wrong.

**Case E — discovery disabled while keeping operations:**

```bash
java -jar target/endpoint-lab-1.0.0.jar --management.endpoints.web.discovery.enabled=false
```

Check:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18080/actuator
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18080/actuator/info
```

Expected stdout:

```text
404
200
```

These results apply to the minimal application described. If security, proxies, colliding controller paths, or external configuration are added, analyze those new layers rather than treating this result table as a universal rule for every system.

## 12. Fixing the Exact Identified Layer and Re-verifying

| Evidence found | Appropriate remediation |
| --- | --- |
| Required dependency missing at runtime | Add the right dependency if that capability is an application requirement; repackage |
| Endpoint disabled individually or by default | Intentionally adjust enablement for the needed endpoint |
| Endpoint excluded on HTTP | Adjust the right exclude source according to exposure policy |
| Only JMX include configured | Configure HTTP exposure if the app actually needs to serve HTTP |
| Property overridden by higher-precedence source | Fix the effective source or remove the incorrect override |
| Base path/port/path mapping changed | Update caller URLs, monitoring tools, or proxy routes |
| Endpoint returns 401/403 | Fix credentials, permissions, or matchers per security requirements |
| Only discovery disabled | Call operation URLs directly; only enable discovery if needed |
| Custom endpoint did not become a bean | Fix bean registration, scan scope, or bean creation conditions |
| Only some instances have the endpoint | Compare versions and configs across instances; complete the deployment properly |

After changing, re-test the same URL and method on the exact instance and version. Record both expected and actual results. If the path changed, test the new URL and confirm consumers of the endpoint have been updated.

When reproducing, keep one change per test. Exposing all endpoints, disabling security, and adding multiple libraries simultaneously may make the URL return 200, yet leave you unaware of which condition was originally missing.

## 13. Diagnostic Exercises

### Scenario 1: include has info, yet production returns 404

Shared configuration:

```properties
management.endpoints.web.exposure.include=health,info
```

Effective production configuration:

```properties
management.endpoints.web.exposure.exclude=info
```

Identify the layer causing the absence and the minimal change if production policy allows exposing info.

**Reference:** info is excluded at HTTP exposure. Re-adding `info` to include or setting `management.endpoint.info.enabled=true` does not resolve the exclude conflict. Adjust the right exclude source, keep endpoint protection consistent with policy, and verify after deployment.

### Scenario 2: Cannot open /actuator, yet calling info works

The application has:

```properties
management.endpoints.web.exposure.include=health,info
management.endpoints.web.discovery.enabled=false
```

Explain why you cannot conclude Actuator is not running.

**Reference:** configuration disables the discovery page, not the info operation. A successful direct call to info proves that operation is being served; there is no need to enable all endpoints to restore a links list that is not required.

### Scenario 3: Correct include, wrong port

A Servlet application has main port 18080, context path `/shop`, separate management port 19090, management server base path `/ops`, and web base path `/manage`. There is no custom path mapping for info.

**Reference:** the management URL to test is `http://127.0.0.1:19090/ops/manage/info` if using HTTP and that address is reachable. Do not prepend `/shop` to the separate management URL. After determining the right URL, still check enablement, exposure, endpoint creation conditions, and access permissions.

A solid diagnostic conclusion must state **the specific missing condition**, the confirming evidence, and the verification test. "include is already in YAML" only proves you wrote a configuration value—not that the entire path to the endpoint works.
