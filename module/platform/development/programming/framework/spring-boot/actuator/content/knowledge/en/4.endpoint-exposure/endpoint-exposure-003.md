# Configuring Include and Exclude Lists for HTTP

## 1. Why Select Which Endpoints Are Exposed?

Having Actuator in an application does not mean HTTP callers need access to every management capability. Monitoring systems may only need to check health, while operators need additional application info and diagnostic metrics. The exposure list helps select the endpoints actually needed on the HTTP interface.

Within the scope of this article, **HTTP exposure** means Actuator allows an endpoint to participate in the application's web interface. Whether a specific caller can access it also depends on address, port, path, and security policy.

Three questions must be kept separate:

1. Is the endpoint provided and enabled in the application?
2. Is that endpoint selected to be exposed over HTTP?
3. Does the current HTTP request go to the right place and have permission to access it?

`include` and `exclude` solve the second question. Do not use them to reason about the other two questions.

This article uses Spring Boot 3.3.x behavior; the illustrative experiments use Spring Boot 3.3.0 and Java 21.

## 2. Two Configuration Properties and Input Values

| Property | Meaning | When left unconfigured in Boot 3.3 |
| --- | --- | --- |
| `management.endpoints.web.exposure.include` | Selects endpoint IDs to expose over HTTP | Only `health` is selected by default |
| `management.endpoints.web.exposure.exclude` | Excludes endpoint IDs from the HTTP interface | No additional endpoints are excluded |

Values are **endpoint IDs**, such as `health`, `info`, `metrics`, `loggers`, not URLs or Java method names. If an ID appears in both lists, `exclude` takes precedence. [Spring Boot 3.3 Endpoint Exposure Rules](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing).

Valid example:

```properties
management.endpoints.web.exposure.include=health,info,metrics
management.endpoints.web.exposure.exclude=metrics
```

In an application where all three endpoints are available and enabled, the result exposes `health` and `info`; `metrics` is excluded. The order of names in the string does not change the precedence order between the two properties.

The following values are not valid ways to select an endpoint:

```text
/actuator/health
http://localhost:8080/actuator/health
GET /actuator/health
health.read
```

They confuse IDs with paths, URLs, or operation names. In configuration, use `health`.

### 2.1. A New Include List Does Not Automatically Add Health

If you write:

```properties
management.endpoints.web.exposure.include=info
```

then the selected list is `info`, not `health,info`. In a test application without security filters, GET `/actuator/info` returns 200, while GET `/actuator/health` returns 404.

If both are needed, both must be written explicitly:

```properties
management.endpoints.web.exposure.include=health,info
```

This is an easy mistake to make when an application is already being checked by a monitoring system at `/actuator/health`: adding an endpoint to configuration by replacing the whole list can accidentally drop the health check endpoint.

### 2.2. Configuring Exclude Alone Does Not Mean Selecting All Other Endpoints

Example:

```properties
management.endpoints.web.exposure.exclude=env
```

If no source changes `include`, the exposure list still follows the default of `health`. This configuration does not automatically expose `info`, `metrics`, or all other endpoints. `exclude` only removes items from the already selected set.

## 3. Computing the Result When Both Include and Exclude Are Present

You can visualize the standard filter as follows:

```text
Endpoint meets existence and enabled conditions
    → is it selected by include?
    → is it excluded by exclude?
    → if selected and not excluded: belongs to HTTP exposed set
```

Let `U` be the set of endpoints that can be provided under the current enablement conditions; `I` is the set of selected IDs and `E` is the set of excluded IDs. In the simple model, without custom filters:

```text
HTTP exposed set = (U intersect I) minus E
```

This calculation helps explain the configuration; it does not replace verifying the actual path and access permissions.

| Effective include | Effective exclude | Result for health / info / metrics, assuming all three exist and are enabled |
| --- | --- | --- |
| Unset, uses default | Unset | Only `health` |
| `health,info` | Unset | `health`, `info` |
| `health,info,metrics` | `metrics` | `health`, `info` |
| `info` | Unset | Only `info` |
| `health` | `info` | Only `health`; excluding `info` adds no endpoint |
| `*` | `metrics` | Selects eligible endpoints, except `metrics` is excluded |
| `*` | `*` | Exposes no Actuator endpoints over HTTP |

Example of a disabled endpoint:

```properties
management.endpoint.info.enabled=false
management.endpoints.web.exposure.include=health,info
```

`info` is named in `include` but is not enabled, so it cannot be accessed over HTTP. Conversely, excluding an endpoint via `web.exposure.exclude` only expresses an HTTP exposure decision; it is not a command to disable it across all management channels.

Similarly, putting `prometheus` into the list does not automatically add the library providing that endpoint. With the minimal project in this article, there is no `micrometer-registry-prometheus`, so GET `/actuator/prometheus` still returns 404 when listed in `include`.

## 4. Writing Configuration in Properties and YAML

### 4.1. Explicit Lists

In `application.properties`:

```properties
management.endpoints.web.exposure.include=health,info,metrics
management.endpoints.web.exposure.exclude=metrics
```

Equivalent in `application.yml`:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - metrics
        exclude:
          - metrics
```

You can also write a YAML list as a comma-separated string:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics"
        exclude: "metrics"
```

Choose one consistent representation for easier review. The snippets above are alternatives for each other; do not copy multiple same-level `management` blocks into the same YAML document.

### 4.2. Selecting All with an Asterisk

In properties:

```properties
management.endpoints.web.exposure.include=*
management.endpoints.web.exposure.exclude=env,configprops
```

In YAML:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
        exclude:
          - env
          - configprops
```

The asterisk must be quoted in YAML because `*` has special meaning in YAML syntax. In properties files, write `include=*`; quotes are not needed to wrap the string as in YAML.

`*` is the supported select-all value. Do not generalize it into name patterns like `health*`, `*metrics`, or path patterns `/**`. In testing with Boot 3.3.0, `include=health*` causes configuration initialization to reject an ID containing invalid characters, rather than selecting endpoints prefixed with `health`.

When using `include=*`, the exposed set can grow after adding libraries or custom endpoints. An explicit list fits when you need exact control over which capabilities are exposed; selecting all and excluding some IDs requires re-reviewing whenever the endpoint set changes.

### 4.3. Excluding All Endpoints from HTTP

In properties:

```properties
management.endpoints.web.exposure.exclude=*
```

In YAML:

```yaml
management:
  endpoints:
    web:
      exposure:
        exclude: "*"
```

This rule still wins over an existing `include` list. It removes Actuator endpoints from the HTTP interface; it does not mean shutting down the web server or deleting business controllers. [HTTP Management Configuration, Including Excluding All Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html#actuator.monitoring.disabling-http-endpoints).

## 5. Standalone Runnable Experiment

The objective is to observe the same application while its HTTP endpoint list changes with configuration. The project adds no Spring Security, has no business controllers, and listens only on loopback so results focus on the exposure filter.

JDK 21, Gradle 8.5, and an internet connection for downloading dependencies on the first build are required. Check `java -version` and `gradle --version` before running.

### 5.1. Creating the Files

```text
actuator-http-exposure-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/exposure/ExposureApplication.java
    └── resources/application.properties
```

File `settings.gradle`:

```groovy
rootProject.name = 'actuator-http-exposure-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}

tasks.named('bootJar') {
    archiveFileName = 'actuator-http-exposure-demo.jar'
}
```

File `src/main/java/example/exposure/ExposureApplication.java`:

```java
package example.exposure;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ExposureApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExposureApplication.class, args);
    }
}
```

File `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8080

management.endpoints.web.exposure.include=health,info,metrics
management.endpoints.web.exposure.exclude=metrics
```

You do not need to write a custom Java endpoint to test this rule; `health`, `info`, and `metrics` are sufficient to demonstrate selecting and then excluding.

### 5.2. Building and Running

In the directory containing `build.gradle`:

```shell
gradle bootJar
java -jar build/libs/actuator-http-exposure-demo.jar
```

The first command builds the JAR; the second runs the application and keeps that terminal window active. Open another window to send requests. On Windows PowerShell, use `curl.exe` if `curl` is mapped to an alias.

```shell
curl -i http://127.0.0.1:8080/actuator/health
curl -i http://127.0.0.1:8080/actuator/info
curl -i http://127.0.0.1:8080/actuator/metrics
```

Key results of the sample project:

| Request | HTTP code | Explanation |
| --- | --- | --- |
| GET `/actuator/health` | 200 | In include, not excluded |
| GET `/actuator/info` | 200 | In include, not excluded |
| GET `/actuator/metrics` | 404 | Excluded even though also in include |

In the newly created sample project, no application info source has been added yet, so the `info` response body is:

```json
{}
```

`200` with `{}` means the endpoint is exposed and handled the request, though it has no info data to return yet. It differs from `404` caused by having no matching mapping in this experiment. Do not insist that all headers or 404 error bodies be identical across machines.

You can open the `/actuator` discovery page to inspect the links exposed in the sample configuration. Not seeing a link there is an inspection clue, not universal proof: the discovery page has its own configuration and can also be subject to access control.

### 5.3. Testing Exclude Precedence

Stop the application with Ctrl+C, then run the same JAR again with the include list passed on the command line:

```shell
java -jar build/libs/actuator-http-exposure-demo.jar --management.endpoints.web.exposure.include=health,info,metrics
```

`metrics` still returns 404 because the configuration file still has `exclude=metrics`. Writing the name again in `include` is not a way to remove an element from `exclude`.

To expose `metrics`, edit the source file so `metrics` is no longer excluded, run `gradle bootJar` again, and restart the JAR. Under the sample project's normal setup, editing packaged source files does not automatically update the endpoint interface of a running process.

### 5.4. Testing a Narrower Include List

Keep the original JAR with `exclude=metrics`; stop the process first and run:

```shell
java -jar build/libs/actuator-http-exposure-demo.jar --management.endpoints.web.exposure.include=info
```

When calling again:

```shell
curl -i http://127.0.0.1:8080/actuator/health
curl -i http://127.0.0.1:8080/actuator/info
```

`health` returns 404 and `info` returns 200. This is evidence that an explicit `info` list does not automatically add the default `health`.

## 6. When Configuration Comes from Multiple Sources

Effective properties can come from common files, profile-specific files, environment variables, or command-line arguments. With Boot's default configuration mechanism, command-line arguments can override values from files. Therefore, determine the **final value of each property**, rather than looking at only one file. [Boot 3.3 Configuration Source Precedence](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

For example, the config file has:

```properties
management.endpoints.web.exposure.include=health,info
management.endpoints.web.exposure.exclude=metrics
```

Start with:

```shell
java -jar build/libs/actuator-http-exposure-demo.jar --management.endpoints.web.exposure.include=health,metrics
```

In the experiment with these exact values:

| Effective property | Value |
| --- | --- |
| include | `health,metrics` from command line |
| exclude | `metrics` from config file |

Result: `health` is exposed; `info` is no longer selected; `metrics` is excluded. Do not assume a new include list appends to the old list, or that changing include clears exclude.

When using profiles, inspect both include and exclude for the active environment as well. If only one property is overridden, the other property can still come from another source.

## 7. Scope of HTTP Configuration

### 7.1. Do Not Use web.exposure to Configure JMX

`management.endpoints.web.exposure.*` is for HTTP. JMX exposure configuration has its own branch `management.endpoints.jmx.exposure.*`. Excluding `info` from HTTP is not enough to conclude it has been excluded from JMX; check the corresponding JMX configuration and enablement conditions.

### 7.2. Endpoint Selection Does Not Change IDs When Paths Change

Example changing the path prefix:

```properties
management.endpoints.web.base-path=/manage
management.endpoints.web.exposure.include=health,info
```

The corresponding default paths change to `/manage/health` and `/manage/info`, while the values in include remain `health,info`. Do not change include to `/manage/health`.

The management port and listening address are also separate decisions from endpoint selection. If the application uses a separate management port, requests must be sent to that port. [Management HTTP Path and Port](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html#actuator.monitoring.customizing-management-server-port).

### 7.3. Exposure Does Not Replace Authorization

`include=loggers` selects the `loggers` endpoint, not a "GET-only log viewing" policy. This list selects endpoint IDs; it does not divide read/write permissions by HTTP method. Per-operation access rights must be configured in the appropriate security layer.

In an application with Spring Security, a selected endpoint can still return 401 or 403. That is a different situation from the endpoint being excluded from the HTTP interface. Do not widen `include` or use `include=*` as a default way to fix authentication or authorization errors.

## 8. Diagnostic Sequence and Common Errors

When an endpoint is unreachable, check in a verifiable order:

1. **Right destination:** address, port, context path, management prefix, and path mapping.
2. **Can be provided:** required libraries, dependent beans, and endpoint enablement configuration.
3. **Right effective lists:** endpoint is in include and not in exclude; check profiles and startup arguments too.
4. **Right permissions:** authentication, authorization, and applied HTTP policies.

In the minimal project without Spring Security in this article, an excluded endpoint returns 404. In a real system, a security layer or proxy can alter the response; do not deduce a single cause from just one HTTP status code.

| Mistake | Consequence / fix |
| --- | --- |
| Writing `management.endpoint.web.exposure.include` | Wrong config branch; correct name uses plural `endpoints` |
| Writing a full URL in include | Confuses ID with address; use `health`, `info`, `metrics` |
| Writing only `include=info` when health is still needed | Write `include=health,info` explicitly |
| Setting only `exclude=env` and expecting all other endpoints to appear | Exclude does not automatically expand the default include set |
| Same ID in both include and exclude | Exclude wins; fix the exclusion list in the effective source |
| Using `include: *` in YAML | The asterisk must be enclosed in quotes in YAML |
| Using `health*` as a prefix pattern | Not a supported ID pattern; can prevent the application from starting |
| Selecting a disabled endpoint or one missing a library | Include neither creates an endpoint nor enables it |
| Editing application.properties but running the old JAR | Rebuild when changing packaged config, then restart |
| Editing the right file yet results do not change | Check active profiles and overriding configuration sources |
| Assuming exclude disables all controllers or all channels | This is an HTTP exposure filter for Actuator endpoints |

## 9. Self-check Exercises

**Question 1.** Which of the three endpoints does `include=health,info,metrics` and `exclude=info` expose?

**Answer:** `health` and `metrics`, provided they are available and enabled. `info` is excluded because exclude takes precedence.

**Question 2.** Does writing only `exclude=metrics` cause `info` to be exposed?

**Answer:** No. If include still follows the default, only `health` is selected. Excluding one element does not add the rest.

**Question 3.** Does `include=*` make the Prometheus endpoint appear in the sample project?

**Answer:** No. The project lacks the library required to provide the Prometheus endpoint. The asterisk selects eligible endpoints; it does not add dependencies.

**Question 4.** Command-line arguments change include to `health,metrics`, while the file still has `exclude=metrics`. Why does metrics not appear?

**Answer:** The two properties are resolved separately. The new include is effective, but exclude from the file still excludes metrics.

**Question 5.** If the base path changes to `/manage`, should the list be `/manage/health,/manage/info` or `health,info`?

**Answer:** Still `health,info`. The list uses IDs; the base path determines the HTTP address.

**Question 6.** Why should `health,info,metrics` be listed explicitly if an environment only needs those three endpoints?

**Answer:** Reviewers directly see the selected scope. When another endpoint is added to the application, it is not automatically exposed merely because an asterisk was used earlier.
