# Managing Contributors via management.info and Default Configuration

## 1. What Is a Contributor and Why Does It Need Management?

The `info` endpoint returns descriptive application information, such as build version, commit ID, or service name. Each component that provides a piece of data is called an `InfoContributor`. The endpoint collects data from these beans to produce the response.

For example, the operations team wants to know whether the running application matches the build just deployed. `build` and `git` information are useful for verification; operating system or process details may not need to be exposed. Managing contributors helps select appropriate data instead of exposing all technical details on a single endpoint.

Three kinds of names must be distinguished:

- `info` is the ID of the endpoint.
- `env`, `build`, `git`, `java`, `os`, and `process` are the IDs of built-in contributors in Spring Boot 3.3.x.
- `app`, `release`, or other keys in JSON are the names of contributed data. They are not inherently contributor IDs.

For instance, `EnvironmentInfoContributor` has ID `env` yet reads `info.app.name` and produces the `app` key in the response. To enable this data source you must use `management.info.env.enabled`; setting `management.info.app.enabled` does not control it. [EnvironmentInfoContributor API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/info/EnvironmentInfoContributor.html)

This lesson focuses on Spring Boot **3.3.x**. The minimal example uses 3.3.0; do not extrapolate contributor lists or properties from newer versions to this branch.

## 2. Three Configuration Layers That Must Be Understood Separately

To retrieve data over HTTP, you must consider the endpoint, accessibility, and data sources in turn:

| Configuration layer | Representative property | Question answered |
| --- | --- | --- |
| Enable the endpoint | `management.endpoint.info.enabled` | Is the `info` endpoint enabled? |
| Expose the endpoint over HTTP | `management.endpoints.web.exposure.include` | Is this endpoint exposed over the web? |
| Select contributors | `management.info.<id>.enabled` | Which information sources are auto-configured? |

Spring Boot 3.3 enables the `info` endpoint by default, but exposes only `health` over HTTP by default. Configuring a contributor does not automatically expose the HTTP path. Beyond these three layers, Spring Security rules or network infrastructure can also restrict who can access it. [Enabling and exposing endpoints in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.enabling)

These two configurations solve two different problems:

```properties
management.endpoints.web.exposure.include=health,info
management.info.java.enabled=true
```

The first line exposes the endpoint; the second line adds the Java data source. With only the first line, the endpoint may still return `{}`. With only the second line, Java data may be prepared, yet the endpoint is not exposed over HTTP.

Do not confuse `management.endpoint.info.enabled` with `management.info.enabled`. The second property is not a global switch for this endpoint in Spring Boot 3.3.

## 3. Defaults for Each Contributor in Spring Boot 3.3.x

| ID | Individual enable/disable property | When no individual property is set | Condition or data source |
| --- | --- | --- | --- |
| `build` | `management.info.build.enabled` | Allowed to be enabled by the general default | Typically requires `META-INF/build-info.properties` to create `BuildProperties` |
| `git` | `management.info.git.enabled` | Allowed to be enabled by the general default | Typically requires `git.properties` at the classpath root to create `GitProperties` |
| `env` | `management.info.env.enabled` | Disabled | Reads properties prefixed with `info.` from Spring Environment |
| `java` | `management.info.java.enabled` | Disabled | Java environment information |
| `os` | `management.info.os.enabled` | Disabled | Operating system information |
| `process` | `management.info.process.enabled` | Disabled | Process information |

These default values are listed in the [Spring Boot 3.3 application properties appendix](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

"Allowed to be enabled" does not mean "guaranteed to have data". Creating the `build` or `git` contributor still depends on the corresponding data bean. Metadata files are the usual way auto-configuration creates those beans.

For example:

```properties
management.info.build.enabled=true
```

This line does not run a metadata-generation task, does not create `build-info.properties`, and does not read the version from the build file in place of missing metadata. Likewise, enabling `git` does not make the application run Git commands in the working directory.

Therefore, when `build` and `git` have no input and the other four contributors remain off, a `{}` response is valid. It is not enough to conclude that Actuator is broken.

## 4. What Does management.info.defaults.enabled Actually Do?

### 4.1. Individual Properties Are Evaluated First

For `build` and `git`, the decision logic can be interpreted as follows:

```text
Is management.info.<id>.enabled set?
  Yes -> use the specific true/false value.
  No  -> evaluate management.info.defaults.enabled.
         If defaults is not set -> the general default is true.

Afterward, bean creation conditions and appropriate data must still be satisfied.
```

For `env`, `java`, `os`, and `process`, if no individual property is set, they remain disabled. They do not use the general default to enable themselves automatically.

Consequently:

```yaml
management:
  info:
    defaults:
      enabled: true
```

does not mean enabling all six contributors. In an application without other customizations, it preserves the default mechanism for `build` and `git`; the other four sources must still be enabled individually.

### 4.2. false Is Not a Ban on Every Contributor

Consider the configuration:

```yaml
management:
  info:
    defaults:
      enabled: false
    git:
      enabled: true
    env:
      enabled: true
```

Result:

- `build` is no longer enabled by the general default.
- `git` is explicitly enabled, yet still requires `GitProperties`.
- `env` is explicitly enabled and will read `info.*` data.
- `java`, `os`, and `process` remain disabled because they have not been individually enabled.

The table below assumes the required build/git data beans are available and the application does not replace the contributors itself:

| Configuration | build | git | env/java/os/process |
| --- | --- | --- | --- |
| No properties set under `management.info` | Enabled | Enabled | Disabled |
| Only `defaults.enabled=true` set | Enabled | Enabled | Disabled |
| Only `defaults.enabled=false` set | Disabled | Disabled | Disabled |
| `defaults.enabled=false`, `git.enabled=true` | Disabled | Enabled | Disabled |
| `defaults.enabled=true`, `git.enabled=false` | Enabled | Disabled | Disabled |
| `defaults.enabled=false`, `java.enabled=true` | Disabled | Disabled | Only Java enabled |

The key point to remember is that **the individual value overrides the general default; input conditions must still be met**. These are two separate steps.

### 4.3. Custom Contributors Need Their Own Conditions

The properties above are read by conditional configuration mechanisms. They are not a filter that removes every `InfoContributor` bean from the Spring context.

If the application declares an `InfoContributor` bean without a condition, setting `management.info.defaults.enabled=false` does not automatically exclude that bean. Similarly, adding `management.info.release.enabled=false` has no effect on a custom bean if no configuration block reads that property.

Do not treat this as a live toggle while the application is running. In conditional-configuration examples, beans are decided when creating the Spring context; after editing configuration, restart the application to verify.

## 5. Minimal Hands-on Practice: Enabling env and Observing Data

### 5.1. Preparing a Standalone Application

The example is a small Gradle project to run standalone with **JDK 21 and Gradle 8.5**, with access to the dependency repository. Do not add Spring Security or custom contributors in this step. The files below form a complete example; do not copy this build file verbatim to replace the build of an existing module.

File `settings.gradle`:

```groovy
rootProject.name = 'info-contributor-demo'
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
```

File `src/main/java/example/infodemo/InfoDemoApplication.java`:

```java
package example.infodemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InfoDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(InfoDemoApplication.class, args);
    }
}
```

File `src/main/resources/application.yml`:

```yaml
management:
  endpoint:
    info:
      enabled: true
  endpoints:
    web:
      exposure:
        include: "health,info"
  info:
    defaults:
      enabled: false
    env:
      enabled: true

info:
  app:
    name: "info-contributor-demo"
    description: "Contributor demonstration application"
```

In the YAML:

- `management.info.env.enabled` determines whether to create the source that reads the Environment.
- `info.app.*` is the data to be exposed.
- `defaults.enabled=false` keeps the lab independent of whether the classpath happens to include build/git metadata.
- The sample data strings are intentionally fixed so the response is predictable.

### 5.2. Running and Checking

From the project directory, run:

```shell
gradle bootRun
```

Keep the application running, open another terminal, and call:

```shell
curl -s http://localhost:8080/actuator/info
```

If using Windows PowerShell where `curl` is aliased, use `curl.exe` instead of `curl` to invoke the actual curl program.

With this exact minimal application, the response has HTTP 200 and a body equivalent to the one below. JSON is line-wrapped for readability; do not rely on JSON key ordering or whitespace:

```json
{
  "app": {
    "name": "info-contributor-demo",
    "description": "Contributor demonstration application"
  }
}
```

The output key is `app`, not `env`. The contributor name represents the data source; the key name represents the data structure contributed by that source.

### 5.3. Disabling the Data Source While Keeping the Endpoint

Stop the application, then rerun with a command-line property:

```shell
gradle bootRun --args='--management.info.env.enabled=false'
```

Call the same URL again. Given that this lab has not added other contributors, HTTP is still 200 and the body is:

```json
{}
```

The endpoint still exists; only the data source has been disabled. This is how to distinguish a valid empty response from an endpoint access error.

### 5.4. Enabling the General Default Does Not Enable env

Stop the application, then rerun:

```shell
gradle bootRun --args='--management.info.env.enabled=false --management.info.defaults.enabled=true'
```

The minimal project does not configure build/git metadata generation, so the body remains `{}`. The general default property does not flip `env.enabled=false` to `true`, nor does it generate missing metadata.

To test Java information without depending on build/git data, run:

```shell
gradle bootRun --args='--management.info.env.enabled=false --management.info.java.enabled=true'
```

The response includes the `java` key. Specific values depend on the actual JVM; do not copy a fixed Java version as the expected result for every machine.

## 6. Selecting Contributors Based on Deployment Needs

Suppose the requirement is to expose the service description and build version, without exposing Git, operating system, or process details. A clear selective configuration is:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info"
  info:
    defaults:
      enabled: false
    build:
      enabled: true
    env:
      enabled: true
    git:
      enabled: false
    java:
      enabled: false
    os:
      enabled: false
    process:
      enabled: false

info:
  app:
    name: "order-service"
    description: "Order processing service"
```

This configuration selects information sources; it is not a guarantee that `build` will definitely appear. You must verify that the build process generates and packages metadata. If metadata is missing, `app` data can still appear properly while `build` is absent.

The explicit `false` lines help readers see the deployment intent. They also make clear that you should not accidentally enable another source just to work around missing data from another one.

If the project uses Spring Security, keep authentication/authorization rules appropriate for the exposed endpoints. There is no need to expose all endpoints with `include: "*"` just to use `info`.

## 7. Controlling a Custom Contributor

The following example adds a `release` source with its own toggle. This file extends the application in section 5 and is placed at `src/main/java/example/infodemo/ReleaseInfoConfiguration.java`:

```java
package example.infodemo;

import java.util.Map;

import org.springframework.boot.actuate.info.InfoContributor;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ReleaseInfoConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "management.info.release",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
    )
    public InfoContributor releaseInfoContributor() {
        return builder -> builder.withDetail(
            "release",
            Map.of("channel", "stable")
        );
    }
}
```

`InfoContributor` is a functional interface with the method `contribute(Info.Builder)`, so a lambda can be used as shown above. [InfoContributor API in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/info/InfoContributor.html)

Choices made in this example:

- Create the bean only when `management.info.release.enabled=true`.
- When the property is missing or set to `false`, do not create the bean.
- `management.info.defaults.enabled` does not participate in the decision of this custom condition.
- The JSON key `release` is chosen in `withDetail`; it is not automatically inferred from the method name or property name.

Stop the application, then run:

```shell
gradle bootRun --args='--management.info.env.enabled=false --management.info.release.enabled=true'
```

With the original configuration from section 5 and only this extension, the response body is:

```json
{
  "release": {
    "channel": "stable"
  }
}
```

If `release.enabled` is changed to `false`, the response reverts to `{}`. Keep `env.enabled=false` in this experiment so `app` data from another source does not interfere with observation.

If `@ConditionalOnProperty` is removed from the bean method, the bean is always registered whenever the configuration class is loaded. Then setting `release.enabled=false` will not automatically disable it. This is why a custom contributor cannot be controlled merely by setting a property name that looks like a built-in configuration property.

## 8. Troubleshooting by the Right Layer

| Symptom | What to check first | How to resolve |
| --- | --- | --- |
| HTTP 200, body `{}` | Which contributors are enabled? Is there metadata or `info.*`? | Enable the right source and verify that source's data |
| `info.app.name` present but no `app` in JSON | `management.info.env.enabled` | Enable `env`; place data under `info.*` |
| `build` enabled but no `build` key | `BuildProperties` bean and packaged metadata | Check build output and classpath, not just the config file |
| `defaults.enabled=false` set yet data still appears | An individual property is `true` or there is a custom contributor | Check registration conditions for each source |
| `defaults.enabled=true` set yet no Java/OS | These sources are disabled individually by default | Explicitly set `management.info.java.enabled` or `os.enabled` |
| HTTP 404 | URL, port, base path, endpoint enablement, and web exposure | Check routing/exposure before modifying contributors |
| HTTP 401 or 403 | Authentication/authorization rules and upstream infrastructure | Check access control layer; enabling a contributor does not grant permission |

Do not treat an HTTP status code as absolute proof of a single root cause: proxies or security rules can alter error responses. The table helps choose the order of investigation.

Common configuration mistakes:

1. **Wrong YAML location.** `info.app.name` sits at the root `info`; do not place the data under `management.info.app.name`.
2. **Singular/plural mix-up.** `management.endpoint.info.enabled` controls a single endpoint; `management.endpoints.web.exposure.include` configures exposure for multiple endpoints.
3. **Confusing the env contributor with the env endpoint.** Enabling `management.info.env.enabled` does not expose `/actuator/env`; it only adds `info.*` data to `/actuator/info`.
4. **Forgetting configuration override sources.** In this example, command-line arguments override values in `application.yml`. When diagnosing other environments, inspect active profiles and effective configuration sources.
5. **Expecting immediate changes without restarting.** The examples use startup bean creation conditions; editing files does not guarantee the context recreates itself.

Regarding exposed data, put under `info.*` only information intentionally chosen to be returned to callers. Do not place passwords, tokens, or connection strings containing credentials there. Do not assume that the `env` endpoint's value-masking mechanism automatically masks `EnvironmentInfoContributor` data; those are two separate data delivery paths. To avoid unintentional data overwrites, custom contributors should also use dedicated keys instead of reusing `build`, `git`, or keys of other sources.

## 9. Self-Check Your Understanding

Predict the outcome before running tests. Assume the endpoint is exposed and the caller has access permission:

| Scenario | Outcome to predict |
| --- | --- |
| `info.app.name` present, `env` not enabled, no metadata or custom contributors | HTTP 200 with `{}` |
| `defaults.enabled=false`, `env.enabled=true`, `info.app.name` present | `app` key is present |
| `defaults.enabled=false`, `git.enabled=true`, no `GitProperties` | No `git` key solely from the switch |
| `defaults.enabled=true`, `java.enabled` not set | `java` key does not appear automatically |
| `defaults.enabled=false`, custom bean with no condition | That bean can still contribute data |
| `release.enabled=false`, using the exact configuration class in section 7 | `releaseInfoContributor` bean is not created |

After this lesson, you should be able to explain three points: **exposing the endpoint**, **enabling a contributor**, and **having input data** are three separate concerns. When you want to change returned information, identify the right contributor, check whether an individual value overrides the default, and then verify the data source and bean registration conditions.
