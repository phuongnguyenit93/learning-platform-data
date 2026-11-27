# Configuration Precedence, Environment Variables, and Command-Line Arguments

## Goals and Context

A **Spring Cloud Task** application handles finite work such as invoice aggregation, data ingestion, reconciliation, or running a Spring Batch Job. When launched in development, testing, and production environments, the same JAR file can use **different configurations** without recompiling. This is especially important for the `TaskRepository` `DataSource`, timeouts, processing batch sizes, profiles, secrets, and per-run business arguments.

For example, a reconciliation task has `task.worker.batch-size=200` in `application.yml`, while Kubernetes sets `TASK_WORKER_BATCHSIZE=500`, and the launch command includes `--task.worker.batch-size=1000`. **What is the final effective value, who overrode whom, and which run does this change affect?** That is the topic of this lesson.

After this lesson, you will be able to:

- Explain how Spring Boot builds the `Environment` from multiple sources and **which source takes precedence**.
- Distinguish packaged configuration, profile-specific configuration, external files outside the JAR, environment variables, Java system properties, and `--...` options.
- Convert property names into environment variables following **relaxed binding** rules.
- Use `@ConfigurationProperties`, `ApplicationArguments`, and placeholders to configure Spring Cloud Task clearly.
- Detect `TaskRepository` override issues, avoid passing secrets on the command line, and verify configuration before deployment.

## 1. Model: Many Sources, One Effective Value

Spring Boot does not restrict configuration to `application.yml`. At startup, the framework builds a collection of `PropertySource` entries inside `Environment`. The same property name can be defined in multiple places; **the higher-precedence source supplies the effective value**. Beans can read values via `Environment`, `@Value`, or strongly typed binding with `@ConfigurationProperties`.

```mermaid
flowchart TD
    A[application.yml and application-{profile}.yml] --> E[Spring Environment]
    B[External files outside JAR / config import] --> E
    C[OS environment and Java -D] --> E
    D[SPRING_APPLICATION_JSON and --key=value] --> E
    E --> F[Spring Boot / Spring Cloud Task bean binding and configuration]
    F --> G[TaskRepository, DataSource, ApplicationRunner]
    H[Business args: --business-date=...] --> I[ApplicationArguments]
    I --> G
```

The diagram separates **two ways arguments are consumed**, which does not mean the system automatically segregates them: by default, **every `--key=value` option** after the JAR name is both present in `ApplicationArguments` and placed by Spring Boot into `Environment`. Names like `--business-date=...` are typically read by business logic; names like `--spring.datasource.url=...` are infrastructure configuration; both are still command-line options. The real boundary is determined by your input contract and the caller's permissions.

## 2. Official Precedence Order of Configuration Sources

The [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html) documentation describes the order of `PropertySource` entries. The table below **goes from lowest to highest precedence**: a source lower in the table can override the same property set by a source above it.

| Ascending order | Source | Example / role |
| --- | --- | --- |
| 1 | `SpringApplication` default properties | Programmatic defaults set by the application via `setDefaultProperties(...)` |
| 2 | `@PropertySource` on `@Configuration` classes | Adds custom properties files; registered relatively late |
| 3 | **Config data** | `application.yml`, profile-specific files, files outside the JAR, `spring.config.import` |
| 4 | `RandomValuePropertySource` | `random.*` keys, typically do not affect business keys |
| 5 | **OS environment variables** | `TASK_WORKER_BATCHSIZE=500`, `SPRING_DATASOURCE_URL=...` |
| 6 | **Java system properties** | `java -Dtask.worker.batch-size=700 -jar app.jar` |
| 7–9 | JNDI and servlet context/config parameters | Relevant when running in web/servlet containers |
| 10 | **`SPRING_APPLICATION_JSON`** | JSON containing multiple properties, parsed into a dedicated `PropertySource` |
| 11 | **Command-line options** | `java -jar app.jar --task.worker.batch-size=1000` |
| 12–14 | Test-supplied properties | `@SpringBootTest(properties=...)`, `@DynamicPropertySource`, `@TestPropertySource`; high precedence during tests |
| 15 | Devtools global settings | Relevant only when Devtools is active |

**In typical production setups:** `application.yml` < environment variables < Java `-D` < `SPRING_APPLICATION_JSON` < `--key=value`. This is a helpful rule of thumb, but **not the entire matrix**: profiles, file locations, config imports, and library-added sources can make tracing more nuanced. When verifying in practice, always inspect `Environment` and the property's origin.

In particular, `@PropertySource` is only loaded during `ApplicationContext` refresh. Some configurations such as `logging.*` and `spring.main.*` are read **earlier**, so do not place them in `@PropertySource` expecting to control the startup phase. Keys like `spring.config.name`, `spring.config.location`, and `spring.config.additional-location` must also be available from the **bootstrap phase**, for example via environment variables, Java system properties, or CLI.

## 3. Order Within the Configuration Files Group (Config Data)

In standard setups, Spring Boot searches for `application.properties` or `application.yml` on the classpath and in external locations outside the JAR, such as the current directory, `./config/`, and immediate subdirectories of `./config/`.

The following order runs from lowest to highest precedence among `application` files:

1. `application.yml` **packaged inside the JAR**.
2. `application-{profile}.yml` **packaged inside the JAR**, e.g., `application-prod.yml`.
3. `application.yml` **outside the JAR**.
4. `application-{profile}.yml` **outside the JAR**.

Example packaged contents:

```yaml
# src/main/resources/application.yml
spring:
  application:
    name: settlement-task
  main:
    web-application-type: none

task:
  worker:
    batch-size: 200
    timeout: 30s
```

```yaml
# src/main/resources/application-prod.yml
task:
  worker:
    batch-size: 300
    timeout: 45s
```

When running with the `prod` profile and **no higher-precedence source**, the effective `batch-size` is `300` and `timeout` is `45s`. If you create `./config/application-prod.yml` outside the JAR with:

```yaml
task:
  worker:
    batch-size: 400
```

then when launching from the directory containing `./config/`, `batch-size` becomes `400`, while `timeout` remains `45s`, because the external file only overrides the properties it declares. **The process working directory** affects whether `./config/` is found; in Docker/Kubernetes, check `WORKDIR` and mount paths rather than assuming it is always the directory containing the JAR.

If both `application.properties` and `application.yml` exist in the **same location**, Spring Boot gives precedence to `.properties`; it is best to standardize on one format to keep tracing straightforward. In a multi-document YAML file separated by `---`, a document with higher precedence and a matching profile condition can override an earlier document. Do not assume a profile filename always beats all other sources: **environment variables and CLI options can still override it**.

### `spring.config.location` vs `spring.config.additional-location`

```bash
# Specify exact config locations; replaces the default search list:
java -jar settlement-task.jar \
  --spring.config.location=optional:file:./runtime-config/ \
  --business-date=2026-11-23

# Keep default locations and add an external location for overrides:
java -jar settlement-task.jar \
  --spring.config.additional-location=optional:file:./runtime-config/ \
  --business-date=2026-11-23
```

- `spring.config.location` **replaces** the default search location list; if you accidentally omit the classpath location, packaged config inside the JAR may not load as intended.
- `spring.config.additional-location` **appends** locations to the defaults; this is usually suitable when you want an environment override layer.
- Directory paths require a trailing `/`. The `optional:` prefix allows startup to continue if the location **does not exist**; do not use `optional:` for required configuration, because a mount or path mistake could be silently masked.
- `spring.config.import` inside a file can load additional config data; values in the imported document **can override** the document declaring the import. This is a specific rule to account for when multiple file layers declare the same key.

Import example:

```yaml
spring:
  config:
    import: optional:file:./runtime-config/task-override.yml
```

If `task-override.yml` exists and sets `task.worker.batch-size: 600`, the imported value can override the same key in the file containing `spring.config.import`. `optional:` only handles the **location not found** case; a file that exists but fails to parse will still fail startup. With multiple imports and multiple profiles, use explicit rules rather than guessing the order.

## 4. Environment Variables and Relaxed Binding

Most shells do not support dots `.` or hyphens `-` in ordinary environment variable names. Spring Boot maps a canonical property name (*canonical kebab case*) to an environment variable in three exact steps:

1. Replace every dot `.` with an underscore `_`.
2. **Remove** hyphens `-` (do not replace them with `_`).
3. Convert everything to uppercase.

| Canonical property | Matching environment variable name | Role |
| --- | --- | --- |
| `task.worker.batch-size` | `TASK_WORKER_BATCHSIZE` | Data batch size |
| `task.worker.timeout` | `TASK_WORKER_TIMEOUT` | Worker timeout |
| `spring.application.name` | `SPRING_APPLICATION_NAME` | Task name used by Spring Cloud Task as metadata |
| `spring.datasource.url` | `SPRING_DATASOURCE_URL` | JDBC URL for DataSource/TaskRepository |
| `spring.datasource.username` | `SPRING_DATASOURCE_USERNAME` | DB username |
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` | Active startup profiles |
| `spring.cloud.task.initialize-enabled` | `SPRING_CLOUD_TASK_INITIALIZEENABLED` | Enables/disables Task schema initialization as configured |
| `task.worker.retries[0].delay` | `TASK_WORKER_RETRIES_0_DELAY` | Example of the first element of a list |

Common mistake: setting `TASK_WORKER_BATCH_SIZE` and assuming it will definitely bind to `task.worker.batch-size`. Under canonical `@ConfigurationProperties` rules, the proper name is `TASK_WORKER_BATCHSIZE`. Flexibility across `Environment` and different lookup mechanisms can vary, so **follow one standard naming rule** and test critical properties.

Linux/macOS shell example:

```bash
export SPRING_PROFILES_ACTIVE=prod
export TASK_WORKER_BATCHSIZE=500
export TASK_WORKER_TIMEOUT=60s

java -jar settlement-task.jar --business-date=2026-11-23
```

Equivalent example in **PowerShell**:

```powershell
$env:SPRING_PROFILES_ACTIVE = 'prod'
$env:TASK_WORKER_BATCHSIZE = '500'
$env:TASK_WORKER_TIMEOUT = '60s'

java -jar settlement-task.jar --business-date=2026-11-23
```

Both set the environment **for the process launched afterward**. An already-running JVM process generally does not pick up external environment variable changes automatically. For short-lived Tasks, standard practice is for the launcher to create a new process/pod per run with the corresponding configuration values. In Kubernetes, variables can be injected via `ConfigMap` or `Secret`, though environment-variable `Secret` values still require access control and care not to leak through diagnostic tools.

### `@ConfigurationProperties` Type Conversion

During binding, `TASK_WORKER_BATCHSIZE=500` can become `int 500`, and `TASK_WORKER_TIMEOUT=60s` can become a 60-second `Duration`. Type conversion errors, such as `TASK_WORKER_BATCHSIZE=hello`, typically prevent the configuration bean from being created: the application should **fail fast** before processing transactions rather than silently using a wrong value.

For **maps/lists**, note a special rule: **a list configured in a higher-precedence source usually replaces the entire list**, rather than merging element by element. For maps, keys can be merged according to binding rules, though overlapping keys still follow source precedence. Test this case specifically when configuring lists of endpoints, tenants, or retry policies.

## 5. How Do Java System Properties Differ from Command-Line Options?

Consider two commands:

```bash
# -D is a Java system property: placed BEFORE -jar.
java -Dtask.worker.batch-size=700 -jar settlement-task.jar \
  --business-date=2026-11-23

# --key=value is an application option: placed AFTER the JAR name.
java -jar settlement-task.jar \
  --business-date=2026-11-23 \
  --task.worker.batch-size=1000
```

In the first case, the JVM processes `-D` and puts the value into `System.getProperties()`, which Spring Boot then exposes in `Environment`. In the second case, Boot by default converts `--task.worker.batch-size=1000` into a CLI property source. That option is also available in `ApplicationArguments`. Passing `java -jar ... -Dtask.worker.batch-size=700` **after** the JAR name does not set a JVM system property; the application may treat it as a regular argument.

**Precedence:** CLI option `--...` is higher than Java `-D...`; Java `-D...` is higher than ordinary environment variables. Therefore, if `TASK_WORKER_BATCHSIZE=500`, `-Dtask.worker.batch-size=700`, and `--task.worker.batch-size=1000` are all present, the bound configuration value is `1000`.

Spring Boot also supports `SPRING_APPLICATION_JSON`: for example, an environment variable containing `{"task":{"worker":{"batch-size":800}}}` is parsed into a property source with **higher precedence than Java system properties but lower than CLI options**. Even though the JSON value is passed via an environment variable, it does not sit at the same precedence level as ordinary OS environment variables. In JSON, `null` is treated as a missing value when resolving properties, so you cannot use `null` to clear a value from a lower-precedence source.

```bash
export TASK_WORKER_BATCHSIZE=500
export SPRING_APPLICATION_JSON='{"task":{"worker":{"batch-size":800}}}'

# Without CLI override, effective value is 800.
java -jar settlement-task.jar --business-date=2026-11-23

# With CLI override, effective value is 1000.
java -jar settlement-task.jar --business-date=2026-11-23 \
  --task.worker.batch-size=1000
```

## 6. Spring Cloud Task Example Reading Values by Role

**Practice scenario:** run the `settlement-task` task accepting `--business-date=YYYY-MM-DD` from a scheduler. `batch-size` and `timeout` are operational configuration; parameters related to `DataSource`/`TaskRepository` are infrastructure configuration. The build file needs a **compatible Spring Boot + Spring Cloud** version set, `spring-cloud-starter-task`, and an appropriate JDBC driver. The snippet focuses on binding and does not perform real business writes.

File `src/main/java/com/example/task/SettlementTaskApplication.java`:

```java
package com.example.task;

import java.time.Duration;
import java.time.LocalDate;
import java.util.List;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTask
@EnableConfigurationProperties(TaskWorkerSettings.class)
public class SettlementTaskApplication {

    public static void main(String[] args) {
        SpringApplication.run(SettlementTaskApplication.class, args);
    }

    @Bean
    ApplicationRunner runSettlement(TaskWorkerSettings settings) {
        return args -> {
            List<String> values = args.getOptionValues("business-date");
            if (values == null || values.size() != 1 || values.get(0).isBlank()) {
                throw new IllegalArgumentException(
                        "Exactly one --business-date=YYYY-MM-DD is required");
            }

            LocalDate businessDate = LocalDate.parse(values.get(0));
            if (settings.batchSize() <= 0 || settings.timeout().isNegative()
                    || settings.timeout().isZero()) {
                throw new IllegalArgumentException("Invalid worker configuration");
            }

            System.out.printf("date=%s batchSize=%d timeout=%s%n",
                    businessDate, settings.batchSize(), settings.timeout());
            // Business service uses settings and businessDate here.
        };
    }
}

@ConfigurationProperties(prefix = "task.worker")
record TaskWorkerSettings(int batchSize, Duration timeout) {
}
```

`TaskWorkerSettings` is a **record** constructor-bound by Boot from configuration sources. `ApplicationRunner` reads each run's `business-date` via `ApplicationArguments`. Keeping the two types of data separated in code helps restrict override rights: an API/scheduler can supply a business date, while the deployment decides `batch-size`, timeout, and DB details.

Base configuration file `src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: settlement-task
  main:
    web-application-type: none
  datasource:
    url: ${TASK_DB_URL:jdbc:h2:mem:task_demo;DB_CLOSE_DELAY=-1}
    username: ${TASK_DB_USER:sa}
    password: ${TASK_DB_PASSWORD:}
  cloud:
    task:
      initialize-enabled: true  # Only suitable for test/demo databases.

task:
  worker:
    batch-size: 200
    timeout: 30s
```

In this exercise, the H2 JDBC driver must be on the classpath for the `jdbc:h2:mem:...` fallback to work. **In-memory H2 does not persist Task history across JVMs**, so production must use a persistent RDBMS, manage Task schema migrations, and typically set `spring.cloud.task.initialize-enabled=false` once the schema is created. Never use an empty default password for a production database.

`spring.datasource.*`, `spring.application.name`, and `spring.cloud.task.initialize-enabled` are all Boot/Cloud properties directly tied to `TaskRepository` and Task lifecycle. For instance, overriding `spring.application.name` changes the **Task name in execution history**, affecting dashboard grouping and name-based monitoring. Changing `spring.datasource.url` points the repository to **a different database**, making records appear to "disappear" when querying the old DB. This is why business clients must not be allowed to pass these infrastructure keys arbitrarily.

### Practice Results Table

Assume `application.yml` has `batch-size=200`, `application-prod.yml` has `batch-size=300`, and no external config exists other than the sources listed in each row:

| How it is run | `batchSize()` value | Why |
| --- | --- | --- |
| Only `--business-date=2026-11-23` | `200` | Default in `application.yml` |
| Add `--spring.profiles.active=prod` | `300` | `application-prod.yml` overrides the base value |
| `prod` profile + `TASK_WORKER_BATCHSIZE=500` | `500` | OS env takes higher precedence than config data |
| OS env `500` + `-Dtask.worker.batch-size=700` | `700` | Java system property overrides OS env |
| `-D...=700` + `SPRING_APPLICATION_JSON` setting `800` | `800` | JSON property source takes higher precedence than `-D` |
| All sources above + `--task.worker.batch-size=1000` | `1000` | CLI option takes higher precedence than the runtime sources above |

You do not need to rebuild the JAR between rows: just start a **new process with the new configuration**. If environment variables remain set in your shell from a previous test, clear them when verifying rows that rely only on base values; e.g., Linux/macOS: `unset TASK_WORKER_BATCHSIZE SPRING_APPLICATION_JSON`, PowerShell: `Remove-Item Env:TASK_WORKER_BATCHSIZE,Env:SPRING_APPLICATION_JSON -ErrorAction SilentlyContinue`.

## 7. Different Ways to Read Configuration and What to Know

| Mechanism | Example | When to use |
| --- | --- | --- |
| `@ConfigurationProperties` | `TaskWorkerSettings(int batchSize, Duration timeout)` | Grouped properties, type conversion/validation needed, convenient for testing |
| `@Value` | `@Value("${task.worker.batch-size:200}") int batchSize` | Single value, few properties; use canonical kebab-case in placeholders |
| `Environment` | `env.getProperty("task.worker.batch-size", Integer.class)` | When reading a property dynamically by name or for diagnostics |
| `ApplicationArguments` | `args.getOptionValues("business-date")` | Per-run business arguments, needing handling for missing/duplicate/invalid format |

Do not bind `--business-date` directly into a configuration bean constant if the task treats it as business input, because you can lose duplicate/missing argument validation and blur the boundary between input contracts and deployment policy. With `@ConfigurationProperties`, prefer explicit prefixes like `task.worker.*` over flat keys like `size` or `timeout` that easily collide with other libraries.

If you want to verify *which configuration actually took effect*, you can log **non-sensitive** values after binding:

```java
System.out.printf("batchSize=%d, timeout=%s%n",
        settings.batchSize(), settings.timeout());
```

To trace exact sources, Spring Boot Actuator provides the `env` and `configprops` endpoints, which can report property sources and origins depending on configuration. However, a Task usually runs with `web-application-type: none` and finishes quickly; you should not enable an HTTP server just to inspect configuration. In test environments, you can enable `org.springframework.boot.context.config=TRACE` logging to observe config data discovery/loading, or write a dedicated binding test. **Never enable uncontrolled display of secret values**; Actuator must be access-controlled, and sensitive values must be sanitized.

## 8. Which Command-Line Arguments Are Stored in Task Metadata?

Spring Cloud Task stores run information in `TaskRepository`; metadata includes `TaskExecution` and **the list of command-line argument strings** (typically in the `TASK_EXECUTION_PARAMS` table in the default schema). This has two consequences:

1. `--business-date=2026-11-23` helps operators see which data period the Task was asked to process. You still need to control PII and record an appropriate idempotency key in case of retries.
2. `--spring.datasource.password=...`, `--api-token=...`, or secrets appended as arguments can be persisted longer than the process lifetime and exposed in process inspectors/logs. **Never pass secrets via CLI arguments.**

Do not assume that all OS environment variables, system properties, and configuration files are automatically snapshotted into `TaskExecution`: Task metadata records the actual arguments and outcome fields per the framework's mechanism; it is **not a complete snapshot** of `Environment`. To reproduce a run accurately, record the non-sensitive artifact/deployment config version, commit hash, image digest, and release identifier outside the repository according to operational policy.

### Passing Configuration in Containers and Job Schedulers

Example responsibility split model:

```text
Kubernetes Job / CronJob
    environment: TASK_WORKER_BATCHSIZE=500
    environment: SPRING_PROFILES_ACTIVE=prod
    secret volume: DB credentials
    arguments: --business-date=2026-11-23
         |
         v
Spring Boot Environment --> TaskWorkerSettings, DataSource, TaskRepository
ApplicationArguments  --> business-date (validation, idempotency check)
```

In an API that triggers a Task, **allowlist** business parameter names and types and pass each argument as a discrete element in the launcher's argument list. Do not concatenate user input into a shell command string; do not allow requests to arbitrarily carry `--spring.*`, `--management.*`, or `--task.worker.*` if the caller lacks operational permissions. If your organization needs controlled overrides, define a dedicated audited configuration mechanism instead of letting users bypass controls via CLI options.

## 9. Blocking Configuration Overrides from `--...`

For systems that must strictly lock down deployment-provided infrastructure configuration, Spring Boot allows **excluding command-line options from `Environment`**:

```java
public static void main(String[] args) {
    SpringApplication app = new SpringApplication(SettlementTaskApplication.class);
    app.setAddCommandLineProperties(false);
    app.run(args);
}
```

This is a **drop-in replacement for `main`** in the Section 6 example. From then on:

- `ApplicationRunner` still receives `ApplicationArguments`, so `--business-date=...` is still read for business processing.
- `--task.worker.batch-size=1000` **no longer** overrides `@ConfigurationProperties` through the command-line property source.
- `--spring.profiles.active=prod` and `--spring.config.additional-location=...` are also **no longer** read as CLI configuration sources. Profiles/locations must be selected via environment variables, Java system properties, or other allowed sources.

This decision affects the entire application, including Boot and library options. Only use it when it is an intentional deployment contract you have verified on a real process. Do not use it as a quick patch for conflicting configurations; it is better to identify the exact property source supplying the unwanted value.

## 10. Secret Configuration Sources: Environment, Placeholders, and Config Trees

In the Task example, `spring.datasource.url`, `username`, and `password` control the DB storing execution history; these values must stay consistent across runs if you want to query the same repository. Placeholders can be used in YAML files:

```yaml
spring:
  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}
```

If a variable does not exist and has no default, placeholder resolution can cause invalid configuration or startup failure. This is usually the desired behavior for required values in production. The `${KEY:default}` syntax allows setting a default, but a default value should never be a real password or a URL pointing to a production DB.

When the platform provides a Kubernetes Secret via a **volume** (one file per value), Spring Boot supports loading a **config tree**:

```yaml
spring:
  config:
    import: optional:configtree:/etc/settlement-secrets/
```

Suppose the volume has `/etc/settlement-secrets/spring.datasource.username` and `/etc/settlement-secrets/spring.datasource.password` containing credentials; Spring Boot can expose them as the corresponding properties. This location must exist and be mounted with proper permissions; in production remove `optional:` if missing secrets must make the Task **fail fast**. Do not print secret file contents, do not dump the raw `Environment` to logs, and do not use `--spring.datasource.password` as an emergency workaround.

**Precedence note:** a config tree loaded via `spring.config.import` belongs to **config data**, so an environment variable or CLI option with the same key can still override it. Mounting a secret file does not automatically lock override rights for that property name. Deployment permissions and control over higher-precedence config sources must still be enforced.

## 11. Symptom-Based Troubleshooting

| Symptom | Possible cause | How to verify and resolve |
| --- | --- | --- |
| `batch-size=200` set in JAR, but task uses `500` | Env var, external file, or CLI overrode it | Check launcher env, `-D`, and arguments list; inspect source in `Environment` |
| `TASK_WORKER_BATCH_SIZE` does not bind as expected | Env var name does not follow canonical relaxed binding | Change to `TASK_WORKER_BATCHSIZE`, test with `@ConfigurationProperties` |
| CLI `--task.worker.batch-size=1000` has no effect | `setAddCommandLineProperties(false)` was called or a higher-precedence test source exists | Check `main`, `PropertySource` list, and runtime environment |
| `prod` enabled, but values come from `application.yml` | Profile is not actually active or profile file was not loaded | Check `spring.profiles.active`, trace config loader, filename, and path |
| External file outside JAR is ignored | Unexpected `WORKDIR`, wrong mount, or `spring.config.location` replaced defaults | Use absolute path/additional location, check files inside container |
| `optional:` enabled and missing config causes no error | Location does not exist, so it is silently skipped | Remove `optional:` for required files, verify mounts before running |
| `TaskRepository` cannot see records from prior runs | DB URL/profile changed so Task wrote metadata to a different DB, or using in-memory H2 | Check effective JDBC URL, Task name, schema/prefix, and persistent DB |
| Config bean throws type conversion error | `batch-size` is non-numeric, `timeout` is malformed or empty | Add validation and fix the value in the highest-precedence source |
| Task succeeds in CI but fails in production | High-precedence test property sources masked runtime values, or missing secrets/permissions | Test with production-like image and deployment config, read bootstrap logs |
| Only part of a list in a profile is applied | Spring Boot overrides the **entire list**, rather than merging by index | Redeclare the full list in the higher-precedence source |

### Step-by-Step Verification Procedure

When encountering an unexpected value in production, proceed in order:

1. **Identify the canonical key and effective value:** e.g., `task.worker.batch-size`, via the bound bean/safe logging, or an `Environment` check in a staging/test environment.
2. **Check highest-precedence sources first:** `--...` args passed by scheduler/launcher; `SPRING_APPLICATION_JSON`; Java `-D`; environment variables.
3. **Check config data:** active profiles, files outside the JAR, `spring.config.location`/`additional-location`/`import`, `WORKDIR`, and mounts.
4. **Check type and semantics:** `Duration`, boolean, list, or map types; whether the namespace is owned by the framework or the application.
5. **Re-run in a controlled manner:** use the same artifact and a sanitized snapshot of non-sensitive configuration; verify Task metadata and business output.

Do not paste full environment dumps or secret contents into chat/logs during investigation; capture only source names and sanitized values. Restrict query access to `TASK_EXECUTION_PARAMS` tables because executed arguments may remain stored there.

## 12. Practice Scenarios

**Scenario A.** `application.yml` sets `task.worker.batch-size=200`; `application-prod.yml` sets `300`; environment has `TASK_WORKER_BATCHSIZE=500`; JVM is invoked with `-Dtask.worker.batch-size=700`; after the JAR name is `--task.worker.batch-size=1000`. The `prod` profile is active. What is the effective value?

**Answer:** `1000` because CLI options by default take higher precedence than Java system properties, environment variables, and config data. If command-line property sources are disabled, among the remaining sources above the effective value is `700`.

**Scenario B.** An operator provides `SPRING_APPLICATION_JSON` containing `{"task":{"worker":{"batch-size":800}}}`, while `TASK_WORKER_BATCHSIZE=500` is also set; there is no CLI override. Result?

**Answer:** `800` because Boot creates a separate property source from JSON that has higher precedence than ordinary environment variables.

**Scenario C.** A scheduler runs `--business-date=2026-11-23 --spring.datasource.url=jdbc:postgresql://another-db:5432/tasks`, after which the dashboard no longer sees new history in the old DB. Why?

**Answer:** Boot can use the `spring.datasource.url` value from the high-precedence CLI option to build a different `DataSource`. If TaskRepository uses that DataSource, metadata is written to the other DB. You must block passing infrastructure keys from requests and verify the actual DB.

**Scenario D.** A `configtree:` properly loaded `spring.datasource.password` from a volume. A user passes `--spring.datasource.password=abc` in the launcher and breaks the connection. Why didn't the secret file win?

**Answer:** `configtree:` is config data, whereas CLI options have higher precedence. Besides fixing the launcher, enforce a policy forbidding overrides of infrastructure keys and never pass passwords on the command line, where they can leak or be persisted in Task metadata.

**Scenario E.** An endpoints list has two items in `application.yml`, while a profile file only defines `endpoints[0]`. Can you assume the second item from the base configuration is still inherited?

**Answer:** Not by default. With `@ConfigurationProperties`, a list from a higher-precedence source usually replaces **the entire list**. Declare the complete list in the overriding source and verify the result after binding.

## 13. Safe Operations Checklist

- [ ] Document the configuration precedence table for your environment; keep one canonical name for each critical property.
- [ ] Keep `application.yml` for non-sensitive defaults; use profiles/external files/environment variables for environment differences.
- [ ] Name environment variables following **dots → `_`, drop `-`, uppercase**; test binding with `@ConfigurationProperties`.
- [ ] Verify `WORKDIR`, mount paths, and the difference between `spring.config.location` and `spring.config.additional-location`.
- [ ] Have the scheduler/API accept only an allowlisted set of business arguments, rejecting arbitrary `spring.*` or `task.worker.*` keys.
- [ ] Never pass tokens/passwords via CLI; use secure secret mechanisms and restrict read access to Task metadata and logs.
- [ ] For the TaskRepository DB, verify the actual effective URL, username, schema, and prefix in each environment.
- [ ] Add validation and clear defaults to `@ConfigurationProperties`, and never silently swallow binding errors.
- [ ] When deploying Spring Batch with Task, inspect Job/Step configuration and retry/restart conditions separately; do not assume CLI arguments automatically become `JobParameters`.
- [ ] Be able to reproduce a run's non-sensitive configuration via image digest, release ID, profile, and config version; monitor exit codes and Task history.

## Official Documentation

1. [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): `PropertySource` order, config data, environment variables, `SPRING_APPLICATION_JSON`, and CLI.
2. [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): `@ConfigurationProperties`, relaxed binding, list and map rules.
3. [Spring Boot — Configuring External Properties](https://docs.spring.io/spring-boot/how-to/properties-and-configuration.html): changing file locations, config loading logs.
4. [Spring Cloud Task — Features](https://docs.spring.io/spring-cloud-task/reference/features.html): DataSource, TaskRepository, table initialization, and Task lifecycle.
5. [Spring Cloud Task — Task Repository Schema](https://docs.spring.io/spring-cloud-task/reference/appendix-task-repository-schema.html): `TASK_EXECUTION` and `TASK_EXECUTION_PARAMS` data for execution observability.

**Key rule to remember:** Spring Boot allows multiple sources to define the same property; **the value from the highest-precedence source that declares the key is used for resolution/binding**, and if that value has the wrong type, binding can fail rather than falling back to a lower-precedence source. In Spring Cloud Task, restrict infrastructure override permissions, pass business parameters per run, and verify that `TaskRepository` connects to the right history store.
