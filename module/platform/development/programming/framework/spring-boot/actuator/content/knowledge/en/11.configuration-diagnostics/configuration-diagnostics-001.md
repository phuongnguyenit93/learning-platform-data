# Using the env Endpoint to Identify Configuration Sources and Precedence

## 1. The problem to solve: the file was edited, yet the application still uses a different value

Suppose `application.yml` declares `demo.message: from-file`, yet the application receives `from-env`. Editing the file again will not necessarily solve the problem: the same configuration key may also be declared in an environment variable, a JVM property, or startup arguments.

Spring aggregates configuration sources into `Environment`. Each source is represented by a `PropertySource` and has a position in the lookup order. When multiple sources provide the same single key, the source with higher precedence determines the selected value; declarations in lower-precedence sources may still exist.

The Actuator `env` endpoint helps answer three questions:

1. **Which source provides this key?**
2. **Which other sources also declare that key but are being overridden?**
3. **Where is the original declaration located, if location information is available?**

This is a diagnostic tool for the `Environment` of the **running process**, not merely a way to re-read a file in the repository. This lesson uses Spring Boot **3.3.x**, JDK **21**, and a non-sensitive test property: `demo.message`.

## 2. The lookup model: following precedence order and finding a source with the key

Consider three sources all declaring `demo.message`:

```text
High precedence
    commandLineArgs     → demo.message = from-cli
    systemEnvironment   → DEMO_MESSAGE = from-env
    application.yml     → demo.message = from-file
Low precedence

The key demo.message is selected from commandLineArgs.
```

There are two common points of confusion:

- The first source in the overall list does not necessarily contain the key being searched. You must find the **first source that provides that key**, rather than mechanically taking `propertySources[0]`.
- The value in the file does not disappear when overridden. It can be selected again after removing the declaration in the higher-precedence source and restarting the application.

Among the commonly used sources of a typical application, you can keep the following abbreviated order in mind, from highest to lowest:

```text
Application arguments --key=value
    > SPRING_APPLICATION_JSON
    > JVM system properties -Dkey=value
    > OS environment variables
    > Configuration data application.properties / application.yml
    > Default properties set by SpringApplication
```

This is **only part of the full order**. Servlet environments, tests, Devtools, and sources added by the application or libraries can introduce additional positions. Do not use the abbreviated diagram to contradict the actual list reported by the application. See [Spring Boot 3.3 externalized configuration order](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

Configuration documentation may list sources in the order where later entries override earlier ones. In the `env` response, `propertySources` is ordered by lookup precedence, with higher-precedence sources appearing first. You need to recognize the direction of the list rather than merely memorizing index numbers.

## 3. Preparing the application and exposing the endpoint

### 3.1. Example prerequisites

Use a Spring Boot 3.3.x web application that already has a main class and the Gradle Wrapper. In the `dependencies` block, ensure you have:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

This snippet is added to a Spring Boot project that already has plugin and dependency management configured, not a standalone complete `build.gradle`. If the project is using WebFlux, keep the existing WebFlux starter; there is no need to add MVC just to read `env`.

The hands-on example assumes no Spring Security, no proxy, and no context path change. For applications that already have security enabled, use the account and access permissions configured for management endpoints.

### 3.2. Configuration for a local machine lab

Place the following content into `src/main/resources/application.yml` of the example application:

```yaml
demo:
  message: from-file

server:
  port: 8080

management:
  server:
    port: 8081
    address: 127.0.0.1
  endpoints:
    web:
      exposure:
        include: "health,env"
  endpoint:
    env:
      enabled: true
      show-values: never
```

In this configuration, the business API uses port `8080`, while Actuator uses port `8081` and listens only on loopback. When merging with an existing configuration, keep a single shared `management` key; do not create two YAML blocks with duplicate keys at the same level.

In Spring Boot 3.3, distinguish between **enabling an endpoint**, **exposing it over HTTP**, and **being authorized to access it**. `enabled: true` does not automatically add `env` to the HTTP exposure list. `show-values` only controls whether values are displayed, not URL access rules.

Do not confuse `management.info.env.enabled` with the configuration in this lesson: that property enables the `info.*` information source for the `info` endpoint, not exposure of the `env` endpoint.

Separating the management port and restricting the management address are described in [Monitoring and Management over HTTP documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html). When running in a container or on a remote machine, `127.0.0.1` belongs to that environment; a terminal on a local machine cannot automatically reach another machine's loopback.

## 4. Choosing the right query mode: the entire environment or a single key

### 4.1. Querying a single key first

With the example above, using Windows PowerShell:

```powershell
curl.exe -i http://127.0.0.1:8081/actuator/env/demo.message
```

On macOS/Linux:

```bash
curl -i http://127.0.0.1:8081/actuator/env/demo.message
```

The `/actuator/env/{property.name}` path is appropriate when the key to investigate is already known. Starting with a specific key avoids reading or sharing an entire list of unrelated configuration.

Suppose the application is started with both an environment variable and a command-line argument. The response below **is abbreviated to keep only the sources that declare the key**, with values masked:

```json
{
  "property": {
    "source": "commandLineArgs",
    "value": "******"
  },
  "activeProfiles": [],
  "defaultProfiles": ["default"],
  "propertySources": [
    {
      "name": "commandLineArgs",
      "property": {
        "value": "******"
      }
    },
    {
      "name": "systemEnvironment",
      "property": {
        "value": "******"
      }
    },
    {
      "name": "Config resource 'class path resource [application.yml]' via location 'optional:classpath:/'",
      "property": {
        "value": "******",
        "origin": "class path resource [application.yml] - 2:12"
      }
    }
  ]
}
```

Read each field in turn:

| Field | How to interpret during diagnostics |
| --- | --- |
| `property.source` | The source selected for the queried key |
| `property.value` | The value the endpoint allows to be displayed; may be masked |
| `propertySources[].name` | Name of each source in precedence order |
| `propertySources[].property` | Declaration of the key in that source, if present |
| `propertySources[].property.origin` | Original location of the declaration, if the source provides this information |
| `activeProfiles` | Profiles currently active |
| `defaultProfiles` | Default profiles; not synonymous with the list of active profiles |

The actual response may contain additional sources that do not provide the key, in which case those entries have no `property`. Source names, resource paths, and line/column locations depend on the application; do not hardcode the illustrative filename strings in verification tools.

The structure of both response formats is described in [Spring Boot 3.3 `env` API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/env.html).

### 4.2. Querying the full environment when broader inspection is needed

```powershell
curl.exe http://127.0.0.1:8081/actuator/env
```

In the full response, each source uses `properties`, which is an object containing multiple keys. Abbreviated example:

```json
{
  "activeProfiles": [],
  "defaultProfiles": ["default"],
  "propertySources": [
    {
      "name": "commandLineArgs",
      "properties": {
        "demo.message": {
          "value": "******"
        }
      }
    }
  ]
}
```

Note the difference in data shape: querying a single key uses `property` on each source, whereas querying the whole environment uses `properties` containing keys. Writing a JSON parser against the wrong shape will lead to concluding that data is missing even though the endpoint is working.

## 5. Experiment: identifying the winning source across three runs

### 5.1. Run with command-line arguments and an environment variable

In a PowerShell terminal dedicated to the lab, save the previous value before setting the variable:

```powershell
$previousDemoMessage = $env:DEMO_MESSAGE
$env:DEMO_MESSAGE = 'from-env'
.\gradlew.bat bootRun --args="--demo.message=from-cli"
```

In another terminal, call `/actuator/env/demo.message`. Expected:

- `property.source` is `commandLineArgs`.
- Declarations from `systemEnvironment` and the configuration file may still appear below.
- With `show-values: never`, values remain `******`; the source information is still sufficient to determine which one wins.

`DEMO_MESSAGE` is the environment variable form used for the `demo.message` key in this example. The actual name in the full list may be `DEMO_MESSAGE`, while querying the key uses `demo.message`. Do not rush to conclude they are two unrelated settings just because the name forms differ.

On macOS/Linux, the equivalent run is:

```bash
DEMO_MESSAGE=from-env ./gradlew bootRun --args='--demo.message=from-cli'
```

### 5.2. Removing application arguments while keeping the environment variable

Stop the application with `Ctrl+C`. In the PowerShell terminal where the variable was set, run:

```powershell
.\gradlew.bat bootRun
```

Call the endpoint again. When no other higher-precedence source declares the same key, `property.source` switches to `systemEnvironment`. The file still contains `from-file`, but the environment variable takes precedence.

On macOS/Linux:

```bash
DEMO_MESSAGE=from-env ./gradlew bootRun
```

### 5.3. Removing the test environment variable as well

Stop the application. In PowerShell:

```powershell
$env:DEMO_MESSAGE = $null
.\gradlew.bat bootRun
```

If no other declarations remain, the winning source at this point is the `application.yml` resource. Inspect `origin` to identify the exact resource and declaration location, instead of merely guessing from the filename open in the IDE.

On macOS/Linux, run when the terminal has no exported `DEMO_MESSAGE` and no overriding argument:

```bash
./gradlew bootRun
```

After stopping the application and completing the PowerShell lab, restore the original variable:

```powershell
$env:DEMO_MESSAGE = $previousDemoMessage
```

| Run | Active declarations in the example | Expected selected source |
| --- | --- | --- |
| 1 | Application argument + environment variable + file | `commandLineArgs` |
| 2 | Environment variable + file | `systemEnvironment` |
| 3 | File | `application.yml` resource |

The table assumes no profile, external file, JVM property, or other custom source overrides that key. If the result differs, that very difference is evidence to search for a missing source in the initial hypothesis.

### 5.4. Distinguishing application arguments from JVM properties

With a built executable JAR named `env-lab.jar`, the syntax for the two types of arguments is:

```text
java -Ddemo.message=from-jvm -jar env-lab.jar --demo.message=from-cli
```

`-Ddemo.message=...` goes before `-jar` to set a JVM property. `--demo.message=...` goes after the JAR name so Spring Boot processes it as an application argument. With the default mechanism, the application argument wins in this situation.

Do not pass `-D` to Gradle itself and assume it has become a JVM property of the application process spawned by `bootRun`. When diagnosing, inspect the arguments of the actual Java process and check the `systemProperties` source on the endpoint.

If the application explicitly disables adding command-line arguments to `Environment` via `SpringApplication.setAddCommandLineProperties(false)`, the result will differ. Therefore, rules must be paired with the conditions of the actual startup mechanism.

## 6. Distinguishing source, location, and values used in code

### 6.1. `source` indicates the source layer; `origin` helps locate what needs editing

For example, `systemEnvironment` indicates that the configuration comes from the process environment; by itself, it does not tell you whether the variable was set in the IDE, a script, a service unit, or deployment configuration. The next step is to inspect how that process was started.

For configuration files, `origin` can point to the classpath, an external file, along with line and column numbers. An `application.yml` file outside the JAR and a file with the same name inside the JAR are two different sources. Editing the right filename in the wrong location may still fail to change behavior.

Not every source supports origin. Missing `origin` does not prove the key does not exist; use `property.source` and the declarations in the source list to continue tracing.

### 6.2. Profiles and file loading locations affect the source set

When `activeProfiles` does not match expectations, verify the profile activation configuration and which resources were loaded. Do not merely see an `application-prod.yml` file in the repository and conclude that the process is using it.

Under typical loading, profile-specific files and configuration files outside the JAR can override declarations in lower-precedence default files. `spring.config.import`, custom locations, or multi-document configuration make guessing by filename even less reliable.

Follow the workflow: **check active profiles → find the key → read the winning source → read origin → check the corresponding deployment source**. The list of loaded sources is evidence closer to the process than the order of files in an IDE.

### 6.3. `env` is not a snapshot of every value in beans

`env` provides evidence about `Environment`; it does not prove that every object in the application holds the exact same value as the returned string.

- A declaration may contain a placeholder expression such as `${demo.host}`. When needed, query the referenced key as well to trace the dependency chain.
- Code may use a default value in `@Value`, a field initializer, or custom fallback logic; those values are not necessarily a key declared in `Environment`.
- The configuration binder may convert strings to other types, such as durations. A bean may also have captured its value at initialization time.

If you need to inspect data bound to `@ConfigurationProperties` beans, the `configprops` endpoint is the appropriate complementary diagnostic step. It has its own structure for beans and configuration binding inputs; see [Spring Boot 3.3 `configprops` API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/configprops.html). Do not enable this endpoint merely to replace identifying sources with `env`.

## 7. Masked values can still be used to trace sources

In Spring Boot 3.3, the default for `management.endpoint.env.show-values` is `never`: **all values** are masked, not only keys named password or secret. `******` is not the actual value bound into the application.

| `show-values` | Meaning |
| --- | --- |
| `never` | Do not show real values |
| `when-authorized` | Show to users determined to be authorized to view values |
| `always` | Allow showing to everyone who can access the endpoint, unless a custom sanitizing function continues to apply |

For HTTP, `when-authorized` also depends on authentication status and the roles configured at `management.endpoint.env.roles`. When no specific role is configured, an authenticated user is considered authorized to view values under this default mechanism. That does not replace URL protection rules in Spring Security. This mechanism is described in [Actuator 3.3 sanitization rules](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.sanitization).

Prioritize identifying the source while data remains masked. If you truly need to see values in a **personal local lab application containing no secrets**, you can run once with:

```powershell
.\gradlew.bat bootRun --args="--demo.message=from-cli --management.endpoint.env.show-values=always"
```

In this run, values not masked by a custom mechanism will appear. Showing applies to the `env` endpoint, not just `demo.message`. After stopping and running again without this argument, the `never` setting in the file takes effect again if no other source overrides it.

Do not save full `env` output into logs, tickets, or shared documents without inspecting the contents. Even when values are masked, key names, paths, and origins can still reveal deployment structure.

## 8. Workflow for diagnosing a misconfiguration

1. **Identify the right instance and key.** With multiple replicas, ensure requests reach the process under investigation; avoid comparing two instances as one.
2. **Call the endpoint for a single key.** Read `property.source` before editing any file.
3. **Inspect all sources providing the key.** Cross-check precedence order; distinguish the winning source from overridden declarations.
4. **Follow origin or startup method.** For file-based sources, locate the exact file; for environment/JVM/CLI sources, inspect how configuration is passed to the process.
5. **Verify profiles and bound values when needed.** A valid source alone is not enough to explain all handling inside a bean.
6. **Change the right source according to the deployment mechanism and re-verify.** For typical examples, restart the application; do not assume editing a file will cause every bean to update automatically.

Spring Boot 3.3's built-in `env` endpoint is read-only. Do not assume there is a `POST /actuator/env` API to modify configuration or an automatic bean refresh mechanism; any additional libraries, if present, must be evaluated against their own contracts.

| Symptom | Investigation direction |
| --- | --- |
| HTTP `404` at the expected URL | Check management port, base path/context path, enablement, and HTTP exposure |
| HTTP `401` or `403` | Check authentication, access permissions, and intermediary layers |
| HTTP `200`, value is `******` | Check `show-values`; continue using source information before needing to inspect values |
| Edited `application.yml` but value does not change | Search for the key in higher-precedence sources and verify the exact file/origin |
| Key not found in the full list as expected | Check profiles, loaded resources, and key naming form; try querying the key directly |
| `env` is right but application behavior still differs | Check binding, type conversion, default values, data retained in beans, and the right instance |

HTTP status codes may be affected by security or proxies depending on the application; the table provides investigation directions, not a single deterministic deduction from an error code.

## 9. Self-check exercises

Perform the three runs in Section 5 and record for each run: the winning source, remaining sources declaring the key, origin if available, and value masking state. Then answer:

- Why does changing the file in Run 1 not remove `commandLineArgs`?
- Why can reading `propertySources[0]` without checking for the key lead to a wrong conclusion?
- When all `value` fields are `******`, what evidence still points to the source that needs to be fixed?
- If `origin` points to a file outside the JAR, why might editing the copy with the same name in source code have no effect?
- Why is a value appearing as expected in `env` not yet sufficient proof that every bean has been updated?

The goal is to trace the path **key under investigation → selected source → configuration location or passing mechanism → re-verification on the right process**.
