# Exposing Selected Information from info.* in the Response

## 1. What Does Selecting Application Information Mean?

When operating a service, we often need to know which application we are calling, what purpose it serves, and which team is responsible for it. This slowly changing identification information can appear in the response of `GET /actuator/info`.

In this lesson, **selecting information** means intentionally declaring the values permitted for exposure under the `info.` configuration prefix. Spring Boot provides `EnvironmentInfoContributor`, with ID `env`, to turn that group of properties into data for the `info` endpoint.

For example, we want to expose:

- Service name: `catalog-service`.
- Short description: `Catalog API for learning`.
- Deployment channel: `local`.
- Support team: `learning-team`.

We keep internal operational parameters such as `app.internal-region` outside the `info` group. This is a data-selection choice made when designing configuration: the default contributor does not infer on its own which values are public or internal.

**Scope:** Spring Boot 3.3.x, JDK 21, and HTTP Actuator. The example pins Spring Boot 3.3.0 for reproducibility; there is no need to write a controller or build a custom `info` endpoint.

## 2. Distinguishing Four Components Before Configuring

| Component | Role in this lesson |
| --- | --- |
| `Environment` | The set of Spring configuration sources in use: YAML, properties, environment variables, command-line arguments... |
| `info.*` properties | The group of data the application intentionally prepares for exposure. Here `*` refers to the entire property group. |
| `env` contributor | Reads properties under `info` and adds them to application information. |
| `info` endpoint | Aggregates data from participating `InfoContributor` beans; when exposed over HTTP, returns data at `/actuator/info`. |

`EnvironmentInfoContributor` reads the entire `info` branch; there is no per-field selection step via query parameters. For instance, `info.app.name` becomes the `app.name` field in JSON; the `info` prefix does not appear as a JSON wrapper layer. [EnvironmentInfoContributor API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/info/EnvironmentInfoContributor.html)

Data flow:

```text
application.yml / other configuration sources
              ↓
Environment: info.app.name, info.app.channel, ...
              ↓
EnvironmentInfoContributor (ID: env)
              ↓
Info.Builder → InfoEndpoint
              ↓
GET /actuator/info → JSON
```

`InfoEndpoint` accepts a list of `InfoContributor` instances; therefore, in a real application, the response may also contain data from other contributors. [InfoEndpoint API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/info/InfoEndpoint.html)

### Three Independent Switches

1. **Is the endpoint enabled?** `management.endpoint.info.enabled`.
2. **Is the endpoint exposed over HTTP?** `management.endpoints.web.exposure.include` must contain `info` and must not be excluded by `exclude`.
3. **Is the info.* data source read?** `management.info.env.enabled=true`.

In Spring Boot 3.3, the `env` contributor is disabled by default. Therefore, merely adding `info.app.name` or merely exposing the endpoint over HTTP is not enough for that data to appear. [Auto-configuration conditions for info contributors](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/info/InfoContributorAutoConfiguration.html)

Note: `env` in `management.info.env.enabled` is **an info contributor**. It is different from the `/actuator/env` endpoint; this lesson does not need to expose the `env` endpoint.

## 3. Standalone Runnable Example

The example uses only Web and Actuator, without adding Spring Security or custom contributors. The machine needs JDK 21, Gradle 8.5, and access to download dependencies from Maven Central.

Structure:

```text
info-selection-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/infodemo/InfoDemoApplication.java
    └── resources/application.yml
```

### 3.1. Declaring the Project and Dependencies

`settings.gradle`:

```groovy
rootProject.name = 'info-selection-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
}

group = 'com.example'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

The BOM manages compatible dependency versions for Spring Boot. The Spring Boot plugin provides the `bootRun` task; there is no need to create a custom Java task. [Applying the Spring Boot Gradle plugin](https://docs.spring.io/spring-boot/3.3/gradle-plugin/getting-started.html)

### 3.2. Creating the Startup Class

File `src/main/java/com/example/infodemo/InfoDemoApplication.java`:

```java
package com.example.infodemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InfoDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(InfoDemoApplication.class, args);
    }
}
```

This is the complete startup class. The `bootRun` command below will compile and run this class along with Spring libraries; running `javac` on its own without the dependency classpath will not be sufficient.

### 3.3. Preparing the Exact Data to Expose

File `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

spring:
  application:
    name: catalog-service

app:
  internal-region: zone-a

management:
  endpoint:
    info:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,info
  info:
    defaults:
      enabled: false
    env:
      enabled: true

info:
  app:
    name: "${spring.application.name}"
    description: "Catalog API for learning"
    channel: "${APP_CHANNEL:local}"
  support:
    team: "learning-team"
```

How to read the configuration:

- `spring.application.name` is the application name used in Spring configuration. This value is included in the response because we **explicitly reference** it from `info.app.name`.
- `app.internal-region` remains usable inside the application but sits outside `info`; the example has no other contributor exposing it.
- `management.info.defaults.enabled=false` isolates the experiment from auto-configured contributors enabled by default. Then `management.info.env.enabled=true` explicitly enables the data source being studied. This configuration is not a command to disable all custom `InfoContributor` beans.
- `info.app.channel` references the `APP_CHANNEL` variable; when that variable is not set, `local` is used.
- `server.address=127.0.0.1` keeps the hands-on example on the local machine.

In a project that already has configuration, merge these keys into the existing YAML tree. Do not create two `management:` keys or two `info:` keys at the same level.

### 3.4. Running and Reading the Response

From the project directory, using Gradle 8.5 with JDK 21:

```shell
gradle bootRun
```

If the project already has Gradle Wrapper 8.5, on Windows PowerShell use:

```powershell
.\gradlew.bat bootRun
```

On Linux/macOS use:

```shell
./gradlew bootRun
```

Choose one appropriate command; do not start multiple instances concurrently on port 8080.

Wait until the application finishes starting. From a second terminal, on Windows run:

```powershell
curl.exe -sS http://127.0.0.1:8080/actuator/info
```

On Linux/macOS, replace `curl.exe` with `curl`.

When `APP_CHANNEL` is not set, no override arguments are passed, and the exact example is used, the JSON body is:

```json
{
  "app": {
    "name": "catalog-service",
    "description": "Catalog API for learning",
    "channel": "local"
  },
  "support": {
    "team": "learning-team"
  }
}
```

The JSON above is formatted across multiple lines for readability. HTTP clients may print a single line, and JSON key order is not an API guarantee; the fields and values are what should be verified.

The response has no `info` wrapper, no `spring` tree, and no `app.internal-region`. In JSON, the `app` object comes from `info.app`, not from the root `app` configuration.

## 4. Field Selection Mechanism: Select at Declaration Time, Not by Filtering After Collection

Think of `info` as a publication manifest that the application intentionally prepares.

| Source property | Does it appear via the env contributor in the example? | Reason |
| --- | --- | --- |
| `info.app.description` | Yes | Belongs to the `info` branch. |
| `spring.application.name` | Yes, under `app.name` | Referenced through `info.app.name`. |
| `app.internal-region` | No | Does not belong to `info` and is not referenced into it. |
| `server.port` | No | Not automatically copied into `info`. |
| A new key `info.support.contact` | Yes when declared | The default contributor reads the entire `info` branch, not only the initial fields. |

Therefore, naming properties `info.private.*` or `info.internal.*` does not make them private data. Those branches still sit under `info`. Similarly, `management.endpoints.web.exposure.exclude=env` only excludes the `env` endpoint from HTTP; it does not exclude any fields from the `info` response.

There is no default `management.info.env.include` / `management.info.env.exclude` filter to select only certain subkeys. If the application must guarantee a fixed set of fields even if someone adds `info.*` keys, disable the `env` contributor and design a custom `InfoContributor` that takes only approved keys. That is an extension step; the main example here solves the requirement through configuration.

Spring Boot 3.3's `EnvironmentInfoContributor` source code places the `info` branch data into a map and passes those details to `Info.Builder`; it does not enforce a key-name-based security policy. Thus, do not rely on names like `password` or `token` to expect data to be automatically masked in the `info` response. [EnvironmentInfoContributor source code](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/info/EnvironmentInfoContributor.java)

In practice, select fields for identification/support and do not place credentials, API keys, customer data, or links containing secrets into `info.*`. Endpoint access permissions and selecting what data to expose are two separate decisions.

## 5. Placeholders and Effective Configuration Values

The `${property-name}` syntax references a value; `${property-name:default}` adds a fallback value. Environment variables and command-line arguments can supply different values from the YAML file. [Placeholders and configuration source ordering](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.files.property-placeholders)

### 5.1. Changing the Deployment Channel Without Editing YAML

Stop the application with `Ctrl+C`. In PowerShell, set the variable and restart from that same terminal:

```powershell
$env:APP_CHANNEL = 'staging'
gradle bootRun
```

When calling the endpoint again, `app.channel` becomes `"staging"`; the remaining fields match the original example.

The variable must exist in the environment of the process starting the application. Setting the variable in the terminal used to run `curl` does not alter the environment of the application running in another terminal.

To return to the original example, stop the application, remove the variable in the terminal where it was set, and restart:

```powershell
Remove-Item Env:APP_CHANNEL -ErrorAction SilentlyContinue
gradle bootRun
```

Linux/macOS way of passing an environment variable:

```shell
APP_CHANNEL=staging gradle bootRun
```

### 5.2. Overriding the Exposed Field Directly

Stop the running instance, ensure `APP_CHANNEL` is unset, and run:

```shell
gradle bootRun --args="--info.app.channel=canary"
```

The `app.channel` field in the response is `"canary"`. Here the argument overrides the `info.app.channel` property itself, so the placeholder value in YAML no longer determines that field.

The changes above are verified by **restarting**. Editing YAML on disk does not mean the running application automatically reloads configuration. This lesson does not set up a refresh mechanism.

## 6. Experiment Separating the Data Switch and the HTTP Switch

Stop the application before each run, keeping the configuration files unchanged.

### Experiment A: Disabling the info.* Data Source

```shell
gradle bootRun --args="--management.info.env.enabled=false"
```

Call `/actuator/info` again. With this exact example having no custom contributors and default sources disabled, the response is:

```json
{}
```

The endpoint is still exposed over HTTP, but no data is contributed. In another project, the response may still contain data from other contributors; do not conclude that every application returns `{}` when `env` is disabled.

### Experiment B: Keeping Data Yet Not Exposing info Over HTTP

```shell
gradle bootRun --args="--management.endpoints.web.exposure.include=health"
```

Check the HTTP status code:

```powershell
curl.exe -sS -o NUL -w "%{http_code}" http://127.0.0.1:8080/actuator/info
```

In this exact standalone example, the printed output is:

```text
404
```

On Linux/macOS, use `curl` and replace `NUL` with `/dev/null`.

The distinction to remember: `{}` with HTTP 200 shows the endpoint is reachable yet has no details; HTTP 404 in experiment B shows no corresponding HTTP route is exposed. [Enabling and exposing Actuator endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing)

## 7. Common Errors and How to Check

| Symptom | Check closest to the root cause |
| --- | --- |
| `info.*` declared yet missing from the response | Confirm `management.info.env.enabled=true` in effective configuration and verify YAML indentation is correct. |
| Returns HTTP 404 | Check Actuator dependency, endpoint enabled status, HTTP exposure list, `exclude`, exact port, and exact path. The example uses port 8080 and the default `/actuator` prefix. |
| Returns HTTP 401 or 403 in an existing application | Check authentication/authorization rules. Adding `info` to the HTTP exposure list does not grant access permission. |
| Application name does not appear | `spring.application.name` does not automatically become a response field; map it with `info.app.name` as in the example. |
| An unexpected field appears | Find the corresponding `info.*` configuration across loaded sources and check other `InfoContributor` beans. |
| Value differs from YAML | Check environment variables, command-line arguments, and active-profile configuration files. |
| Edited file yet response stays stale | Restart to verify the new configuration; do not assume automatic refresh. |
| Internal info exposed even though the `env` endpoint is not exposed | Check data placed or referenced under `info`; the two mechanisms do not share a field allowlist. |

If the service uses Spring Security, the `env` contributor still determines only the content; the endpoint protection policy determines who can read that content. Do not rewrite the entire security configuration just to fix one missing field.

## 8. Hands-on Practice

1. Run the initial example and verify all four selected values are present while `internal-region` is absent.
2. Add `info.support.contact: "support@example.test"` under the `support` branch, restart, and predict the location of the new field.
3. Set `APP_CHANNEL=staging` in the application process environment; confirm only the channel value changes.
4. Disable the `env` contributor; verify the endpoint remains reachable while data from the `info` branch disappears.
5. Restore configuration, expose only `health` over HTTP, and verify status 404 when calling `info`.

Verification answers: step 2 adds the `support.contact` field; step 3 changes `app.channel` to `"staging"`; step 4 returns `{}` in this exact sample project; step 5 no longer provides the `/actuator/info` HTTP route.

After this lesson, learners should be able to explain the path **selected properties → info.* → env contributor → info response**, as well as select fields from configuration, verify effective values, and distinguish missing-data errors from unreachable-endpoint errors.
