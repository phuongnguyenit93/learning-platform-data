# Launching with Arguments and Deployment Properties in Spring Cloud Data Flow

## 1. Context: One Task, Multiple Launches with Different Configurations

**Spring Cloud Task** helps you build Spring Boot applications with a finite runtime, tracking start/end times, exit codes, and arguments via `TaskExecution` in `TaskRepository`. When operating across many machines or containers, **Spring Cloud Data Flow (SCDF)** provides a way to register applications, define tasks, launch manually, run on schedules, and monitor executions.

Suppose an enterprise has a `dailyclose` application for daily revenue closing:

- On normal days, the task processes `tenant-A` data for yesterday.
- When running backfill, a specific `businessDate` must be passed.
- During peak load, the container memory limit needs to be increased.
- During testing, `dry-run` can be enabled without writing results.
- Across multiple deployment environments, JDBC URLs, secrets, and worker resources differ.

Instead of repackaging the application for every run, we separate **business arguments**, **application configuration**, and **deployment properties**. These three groups have different responsibilities and flow through different infrastructure layers.

> **Do not confuse roles:** Spring Cloud Task is the framework that runs the application and writes metadata; Spring Cloud Data Flow is the orchestration platform for registering, launching, scheduling, and observing tasks. A Spring Cloud Task application can run via `java -jar` or a Kubernetes Job **without** SCDF.

## 2. Distinguishing Task Application, Task Definition, and Task Execution

| Concept | Example | Meaning |
|---|---|---|
| Task application | Artifact/image `dailyclose` | Registered Spring Boot + Spring Cloud Task codebase |
| Task definition | Name `daily-close` with definition `dailyclose` | Logical SCDF configuration used at launch |
| Task launch | User/scheduler requests a task run | SCDF forwards the request to TaskLauncher |
| Task platform | Local, Kubernetes, or configured platform | Where the launcher creates the process/container |
| Task execution | A single application run with an ID | Metadata in TaskRepository/SCDF |
| Application arguments | `--date=2026-11-23`, `--tenant=tenant-A` | Inputs for a single business processing run |
| App properties | `app.dailyclose.report.format=csv` | Task's Spring Environment configuration at launch |
| Deployer properties | `deployer.dailyclose.kubernetes.limits.memory=1024Mi` | Directives for the platform deployer, not business logic |

The same `task definition` can be launched many times, creating many `TaskExecution` records. Runs may differ in arguments or resources, yet metadata and business results must still be carefully distinguished.

~~~mermaid
flowchart TD
    U["User / Scheduler / API"] --> DF["Spring Cloud Data Flow"]
    DF --> TD["Task definition: daily-close"]
    TD --> L["TaskLauncher on task platform"]
    L --> P["JVM / container dailyclose"]
    P --> A["Spring Boot + Spring Cloud Task"]
    A --> R["ApplicationRunner / business service"]
    A --> TR["TaskRepository: TaskExecution"]
    R --> BD["DB / files / target systems"]
    DF --> M["Task execution monitoring"]
    TR --> M
~~~

The diagram is an architectural model. How the platform delivers app properties or deployer properties depends on the configured TaskLauncher.

## 3. Three Parameter Groups: Arguments, App Properties, and Deployer Properties

| Mechanism | Form in SCDF Shell | Who Consumes It? | Example |
|---|---|---|---|
| **Launch arguments** | `--arguments "..."` | Application receiving arguments at startup | `--date=2026-11-23 --dry-run` |
| **Application properties** | `--properties "app.<app>.key=value"` | Application's Spring Environment | `app.dailyclose.report.format=csv` |
| **Deployment properties** | `--properties "deployer.<app>.<platform>.<key>=value"` | Deployer/TaskLauncher | `deployer.dailyclose.kubernetes.limits.cpu=1000m` |

`<app>` is the application name or label in the task definition according to SCDF syntax and your active version. In composed tasks with multiple apps, you must target the right **node label** rather than applying the same key to all of them.

**Quick selection rule:**

- If the value varies by the **business intent of a run** (date, tenant, job ID, dry-run), prefer **arguments**.
- If it is a **Spring setting of the application** (output format, batching strategy, non-sensitive log level), consider **`app.*`**.
- If it controls **how the platform creates the process/container** (CPU, RAM, image pull policy, working directory), use **`deployer.*`**.
- If it is a **secret**, prefer a secret manager/secret reference and supported platform configuration rather than putting raw values in arguments or properties.

Choosing the right channel also tells you whether a parameter belongs in **TaskRepository** or is managed by the **platform**: task metadata can record launch arguments, but you should not assume it stores all deployer properties.

## 4. Standard Workflow: Register App, Create Task Definition, and Launch

Assume the task application is packaged and registered as `dailyclose` in SCDF under type `task`. Registration can use a Maven artifact, container image, or URI source supported by the platform; exact syntax and URIs depend on your version/deployer.

In Spring Cloud Data Flow Shell, create the task definition:

~~~text
dataflow:> task create --name daily-close --definition "dailyclose"
~~~

Launch without extra arguments:

~~~text
dataflow:> task launch daily-close
~~~

Launch with business arguments:

~~~text
dataflow:> task launch daily-close --arguments "--date=2026-11-23 --tenant=tenant-A --dry-run"
~~~

Combine arguments and application properties:

~~~text
dataflow:> task launch daily-close --arguments "--date=2026-11-23 --tenant=tenant-A" --properties "app.dailyclose.report.format=csv"
~~~

Example increasing Kubernetes resource limits at launch:

~~~text
dataflow:> task launch daily-close --arguments "--date=2026-11-23 --tenant=tenant-A" --properties "deployer.dailyclose.kubernetes.requests.cpu=500m,deployer.dailyclose.kubernetes.limits.cpu=1000m,deployer.dailyclose.kubernetes.requests.memory=640Mi,deployer.dailyclose.kubernetes.limits.memory=1024Mi"
~~~

**These commands are SCDF Shell syntax**, not Java, Spring Boot CLI, or `kubectl` commands. When running only `java -jar`, there is no SCDF `app.dailyclose.*` or `deployer.dailyclose.*` layer: the application receives args directly along with its own Spring property sources.

### Why Does the Same Name Appear in Multiple Places?

In the example:

- `dailyclose` is the **registered application name** in the definition.
- `daily-close` is the **task definition name** launched by the operator.
- `app.dailyclose.*` and `deployer.dailyclose.*` target **application `dailyclose`**.
- `spring.cloud.task.name`, if present, is used by the framework to determine the TaskExecution name; do not automatically equate every displayed name, especially in composed tasks.

If the task definition has multi-node DSL or different labels, keys must change to match the targeted node. Always inspect the **actual definition** before concluding that a "property was not applied."

## 5. How Spring Boot Reads Arguments Inside the Application

Spring Boot offers two common approaches:

- `CommandLineRunner.run(String... args)` receives the raw argument array.
- `ApplicationRunner.run(ApplicationArguments args)` receives arguments parsed into option and non-option arguments.

For input `--date=2026-11-23 --tenant=tenant-A --dry-run`, `ApplicationArguments` is well suited for structured reading:

~~~java
import java.time.LocalDate;
import java.util.List;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class DailyCloseRunnerConfiguration {

    @Bean
    ApplicationRunner dailyCloseRunner(DailyCloseService service) {
        return args -> {
            String tenant = required(args.getOptionValues("tenant"), "tenant");
            LocalDate date = LocalDate.parse(
                required(args.getOptionValues("date"), "date"));
            boolean dryRun = args.containsOption("dry-run");

            // Must wait for the service to finish, not fire-and-forget.
            service.closeDay(tenant, date, dryRun);
        };
    }

    private static String required(List<String> values, String name) {
        if (values == null || values.size() != 1
                || values.get(0) == null || values.get(0).isBlank()) {
            throw new IllegalArgumentException(
                "Missing --" + name + "=...");
        }
        return values.get(0);
    }
}
~~~

`DailyCloseService` is a project-built business component. The snippet illustrates the entry point and validation, **not a full application with complete schema/repository setup**.

### Common Mistakes

`ApplicationArguments.containsOption("dry-run")` checks for the **presence** of the option, rather than parsing a boolean string. `--dry-run=false` still makes `containsOption("dry-run")` return `true`. If you want to support toggling via value, read `getOptionValues("dry-run")` and validate explicit rules.

`getOptionValues("date")` can return `null`, an empty list, or multiple values if the user passes duplicates; never assume a first element always exists.

Values like `date` and `tenant` must be validated for access permissions, valid ranges, and idempotency. **SCDF only forwards arguments**; it does not validate business semantics.

## 6. App Properties Go into Spring Environment, Not Necessarily ApplicationArguments

The property `app.dailyclose.report.format=csv` instructs SCDF/TaskLauncher to provide `report.format=csv` to the application. Spring Boot can read it via `Environment` or `@ConfigurationProperties`, for example:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
class ReportFormatter {

    private final String format;

    ReportFormatter(
            @Value("${report.format:json}") String format) {
        this.format = format;
    }

    public String format() {
        return format;
    }
}
~~~

`${report.format:json}` in the example is Spring property placeholder syntax, defaulting to `json`. When `app.dailyclose.report.format=csv` is properly propagated to the Spring Environment, `format()` can return `csv`.

**Do not assume `ApplicationArguments.getOptionValues("report.format")` returns values from `app.*`.** App properties may arrive via environment variables or another platform-chosen mechanism; they do not necessarily appear in the JVM's CLI argument list.

Similarly, `deployer.dailyclose.kubernetes.limits.memory=1024Mi` is a **deployment property**, not a `limits.memory` value for application `@Value` injection. If you need to know the container's actual limits, use platform/cgroups metrics and observability tooling rather than treating deployer properties as business configuration.

## 7. Precedence: Which Property Wins When Declared in Multiple Places?

A task can receive configuration from:

1. `application.yml` packaged inside the artifact.
2. Environment variables or a config server.
3. Common task application properties configured on the SCDF server.
4. Properties in the task definition.
5. App properties specified at launch time.
6. Application command-line arguments, if converted into Spring Boot options.

**There is no single immutable precedence table across all deployment modes.** Inside Spring Boot, the order of property sources determines the effective value; SCDF and TaskLauncher may choose to pass app properties as CLI arguments or environment variables. For example, one deployer may handle values differently from another.

SCDF documentation states that **application properties at launch can override common task application properties**, and in composed tasks, properties specified at launch take precedence over the corresponding configuration in the definition.

Example of common properties on the SCDF server:

~~~properties
spring.cloud.dataflow.applicationProperties.task.report.format=json
~~~

At launch:

~~~text
dataflow:> task launch daily-close --properties "app.dailyclose.report.format=csv"
~~~

The expected result is that the task receives `report.format=csv` per SCDF's override policy, provided the property is forwarded properly. However, if there is also a **CLI option `--report.format=xml`**, Spring Boot may give higher precedence to the command-line property source, depending on how the launcher passes the parameters.

**Recommendation:** do not design workflows that rely on multiple sources overwriting the same critical property. Establish a clear single source of truth, enable safe logging to observe effective properties (without logging secrets), and verify behavior directly on the target deployment platform.

## 8. Platform-Specific Deployment Properties: Local vs. Kubernetes

`deployer.<app>.<platform>.<key>=value` is passed by SCDF to TaskLauncher/Deployer. Property semantics depend on the implementation.

### 8.1. Kubernetes Task Platform

Common Kubernetes deployer keys:

| Property | Meaning |
|---|---|
| `deployer.dailyclose.kubernetes.requests.cpu` | CPU request |
| `deployer.dailyclose.kubernetes.limits.cpu` | CPU limit |
| `deployer.dailyclose.kubernetes.requests.memory` | Memory request |
| `deployer.dailyclose.kubernetes.limits.memory` | Memory limit |
| `deployer.dailyclose.kubernetes.ttlSecondsAfterFinished` | Cleanup time for Job/Pod after completion, depending on version/platform |
| `deployer.dailyclose.kubernetes.environmentVariables` | Environment variables provided by the deployer per supported syntax |

Example setting CPU and RAM:

~~~text
dataflow:> task launch daily-close --properties "deployer.dailyclose.kubernetes.requests.cpu=500m,deployer.dailyclose.kubernetes.limits.cpu=1000m,deployer.dailyclose.kubernetes.requests.memory=640Mi,deployer.dailyclose.kubernetes.limits.memory=1024Mi"
~~~

CPU `1000m` equals one CPU per Kubernetes resource quantity definitions; memory `1024Mi` is one GiB in mebibytes. **A container memory limit does not automatically set the JVM's `-Xmx`**. Check Java container awareness, `JAVA_TOOL_OPTIONS`, heap/GC/native memory, and OOMKill risk.

If a property targets the wrong app label or the deployer does not support the key, the request may be rejected or silently not applied as expected. Inspect the generated Job/Pod YAML (with authorized operational tools) rather than looking only at the SCDF command.

### 8.2. Local Task Platform

The Local deployer spawns a process on a host with a suitable Data Flow task platform; documented example properties:

~~~text
deployer.dailyclose.local.javaOpts=-Xmx1024m
deployer.dailyclose.local.workingDirectoriesRoot=/var/tmp/scdf-tasks
~~~

Do not apply Kubernetes keys to Local and expect Pod-style CPU requests/limits. On the Local platform, memory and CPU isolation depend on the OS and launcher implementation, which is not equivalent to Kubernetes isolation.

### 8.3. Non-Business Properties

Even when using `deployer.*` to increase memory, lower CPU, or change an image, **the processing date and business key must not change**. When retrying the same business work with more RAM, it is still the **same prior business intent**, even though the new TaskExecution has a different resource configuration.

## 9. Defining Application Versions and Reproducibility

A task definition can point to a default app version. SCDF supports specifying an application version in launch properties in matching documentation versions, for example:

~~~text
dataflow:> task launch daily-close --properties "version.dailyclose=3.0.0"
~~~

For reproducible outcomes, production deployments should record:

- The executed artifact/container image **version or digest**.
- Business parameters/JobParameters identifying the same intent, especially `tenant`, `businessDate`, and `revision`.
- Application config version (when processing logic depends on configuration).
- TaskExecution ID and platform execution info for traceability.
- Database/schema version compatible with the application.

Changing the app version while rerunning an old task can alter calculation logic. If **intentional reprocessing** is needed, use a new revision or an output adjustment policy. If it is only a retry after an infrastructure failure, prefer inputs/snapshots with stable identity.

`version.<app>` configuration and version resolution mechanisms can vary by SCDF release; verify against your actual app registry and task launch behavior.

## 10. What Does Spring Cloud Task Store in TaskRepository?

Once a Spring Cloud Task application starts with an appropriate DataSource/schema, it can persist execution metadata:

| Field | Purpose |
|---|---|
| `TaskExecutionId` | Identifies a single run |
| Task name | Task name determined by the resolver |
| Start/end time | Lifecycle tracking |
| Exit code/exit message | Observing technical outcome |
| Arguments | CLI inputs recorded by the framework |
| External execution ID | Link to the orchestration platform if provided |

**TaskRepository is not a deployment configuration store.** Do not assume every `deployer.*` setting or all Pod environment variables appear in TaskExecution. Business results are not automatically stored here either.

With SCDF Shell, you can query:

~~~text
dataflow:> task execution list
dataflow:> task execution list --name daily-close
dataflow:> task execution status --id 549
~~~

`549` is an example ID; replace it with an actual ID in your system. If a task never created a TaskExecution record because it crashed too early on startup, do not conclude "it was never launched" solely from a missing row in the repository: check the Data Flow launch record, TaskLauncher result, and platform logs.

SCDF may maintain its own metadata store for task definitions and launches; the Spring Cloud Task application executing inside the JVM is what provides lifecycle data within its capabilities.

## 11. Differences When the Task Uses Spring Batch JobParameters

If the `dailyclose` application uses Spring Batch, distinguish:

- **SCDF launch arguments:** strings sent to the application.
- **Spring Boot application properties:** Spring Environment configuration.
- **Spring Batch JobParameters:** parameters passed to JobLauncher/JobOperator to identify a JobInstance, carrying an **identifying** flag.

A custom `ApplicationRunner` can read arguments and construct JobParameters:

~~~java
JobParameters parameters = new JobParametersBuilder()
    .addString("tenant", tenant, true)
    .addString("businessDate", businessDate.toString(), true)
    .addLong("revision", 1L, true)
    .addString("traceId", traceId, false)
    .toJobParameters();
~~~

This example illustrates Spring Batch 5, with already-validated variables `tenant`, `businessDate`, and `traceId`. If you use Spring Boot/SCDF auto-launch, the syntax converting CLI arguments into JobParameters **may differ** from a custom runner; do not assume `--date=...` automatically becomes an identifying JobParameter.

**Restarting the right JobInstance:** keep the same Job name and identifying parameter set. Do not add a new timestamp or `run.id` as an identifying parameter just because a new launch was created. A new TaskExecution ID does not mean a new JobInstance.

Deployer properties like CPU/RAM and most logging/formatting app properties should not be confused with JobParameters. If a property **actually changes business output** (such as a source snapshot or algorithm revision), you need an explicit policy to incorporate it into an appropriate identifier, snapshot/fingerprint, or revision.

## 12. Launching via API, Schedules, and Composed Tasks

SCDF provides a REST API and UI for launching in addition to the Shell. When using the API:

- The launch request typically contains the task definition name, argument list, and property map per your API version's schema.
- TaskLauncher passes properties to the platform and arguments to the application according to the deployment contract.
- Security and API authorization determine who can launch tasks with which data.

Because endpoints/payloads can change across releases, consult the OpenAPI/REST reference for your exact Data Flow version rather than copying a mismatched JSON request.

### When Running on a Schedule

With schedules, the task definition and schedule-specific properties are stored/managed by the scheduling feature. Verify:

- Where the date parameter comes from: fixed on the schedule, computed at startup, or passed dynamically by an external scheduler.
- Timezone and business-date resolution rules: avoid relying on uncontrolled default timezones.
- Whether resources/secret channels apply to the actual launch or only the schedule configuration.
- Platform retry/backoff and overlap prevention mechanisms.

A task scheduled daily that is always launched with `--date=2026-11-23` will **always process the same date**; Data Flow does not automatically update business date options just because a new calendar day arrived.

### When a Composed Task Has Multiple Nodes

A composed task may contain `task-a && task-b` or branches. When passing properties, identify the **node label** in the graph. For example, in composed task documentation, `deployer.task-a.kubernetes.limits.cpu=1000m` targets node `task-a`.

Arguments to the composed task runner do not automatically become arguments to every child task. Use the shared/per-node argument syntax supported by your Composed Task Runner version (such as `composedTaskArguments` where applicable), and verify directly in the child execution.

Do not use the `app.dailyclose.*` example on a composed task with different labels without adjusting it.

## 13. Security When Passing Arguments and Properties

**Never pass passwords, tokens, private keys, or connection strings with raw credentials in `--arguments`** if avoidable. Those values can appear in:

- Process lists and JVM command lines.
- TaskExecution arguments in TaskRepository.
- Data Flow launch history, request logs, and audit logs.
- Kubernetes Job/Pod specs and `kubectl describe`, depending on entrypoint style.
- Shell history or CI/CD scripts.

Likewise, `app.*` is not a secure secret store by default. SCDF documentation notes that `entryPointStyle` settings can convert app properties into command-line arguments. Some configurations recommend `shell` or `boot` over `exec` to reduce exposure via args; however, **that alone does not guarantee secrets won't appear in Pod specs or operational tool output**.

On Kubernetes, prefer:

1. Kubernetes Secrets/`secretKeyRef` or an organization-approved secret management platform.
2. Roles/service accounts and RBAC restricting who can read Pods/Secrets.
3. Separation of privileges between the Data Flow server and the task launcher.
4. Never logging full `ApplicationArguments` or dumping Spring Environment when secrets are present.
5. If SCDF provides a mechanism to mount Kubernetes Secrets for database credentials, enable and test it for your exact server version.
6. Secret rotation and verifying workers pick up new values without putting passwords into launch commands.

Example of an application reading DB username/password from the environment:

~~~yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: jdbc:postgresql://db.internal:5432/taskdb
    username: ${DB_USER}
    password: ${DB_PASSWORD}
  cloud:
    task:
      name: dailyclose
~~~

`${DB_USER}` and `${DB_PASSWORD}` in the example are written as Spring placeholders when saved, and must be supplied by an actual secret/environment mechanism.

## 14. A Successful Launch Differs from Business Success

Data Flow can return "task launched" as soon as TaskLauncher accepts creating a process or Pod. That **does not prove** the task processed data successfully.

~~~mermaid
sequenceDiagram
    participant O as Operator / Scheduler
    participant D as Spring Cloud Data Flow
    participant L as TaskLauncher
    participant J as JVM / Pod
    participant R as TaskRepository
    participant B as Business DB

    O->>D: task launch + arguments + properties
    D->>L: Launch request
    L->>J: Create process/container
    L-->>D: External launch info
    D-->>O: Launch accepted
    J->>R: TaskExecution starts
    J->>B: Process business logic
    alt Success
        B-->>J: Commit result
        J->>R: Record completion, appropriate exit code
    else Failure / crash
        B-->>J: Exception or lost connection
        J->>R: May record error if JVM is still alive
    end
    O->>D: Query execution status
~~~

If the application has an `ApplicationRunner` or `CommandLineRunner`, the runner should **only return after mandatory work has actually completed**, rather than dispatching `@Async` work and returning immediately. When a runner throws an exception, let the error affect the exit code rather than logging and continuing.

If the JVM receives `SIGKILL` or a node loses power, TaskRepository may hold an unclosed record. Reconcile the Data Flow launch, Pod/Job status, TaskExecution, and business outcomes before retrying.

## 15. Idempotency When the Same Arguments Are Launched Multiple Times

Suppose an operator launches twice:

~~~text
task launch daily-close --arguments "--date=2026-11-23 --tenant=tenant-A"
task launch daily-close --arguments "--date=2026-11-23 --tenant=tenant-A"
~~~

Two launches can create **two distinct TaskExecutions**. SCDF/TaskRepository does not automatically ensure revenue is recorded only once for the same tenant/date.

An appropriate business key:

~~~text
(tenantId, operation, businessDate, revision)
= (tenant-A, CLOSE_DAY, 2026-11-23, 1)
~~~

The result store should enforce a corresponding unique key/idempotency rule:

~~~sql
CREATE TABLE daily_close_result (
    tenant_id      VARCHAR(64) NOT NULL,
    business_date  DATE NOT NULL,
    revision       INTEGER NOT NULL,
    total_amount   NUMERIC(19, 2) NOT NULL,
    PRIMARY KEY (tenant_id, business_date, revision)
);
~~~

On retry, the service checks the key and decides whether to return the existing result, resume from a checkpoint, or raise a conflict if the source changed. **Do not use TaskExecutionId as a business key**, because it changes on every launch.

Changing `deployer.dailyclose.kubernetes.limits.memory` only changes resource allocation; it does not turn the same business date into a new business operation.

## 16. Diagnosing Argument and Deployment Property Issues

| Symptom | Common Causes | What to Check |
|---|---|---|
| Task starts but does not see `--date` | Invalid `--arguments` syntax, shell quoting/splitting, different definition | Inspect launch request and how `ApplicationRunner` reads args |
| `@Value` still uses default value | Wrong `app.*` prefix, wrong label, or launcher didn't pass it into Environment | Inspect definition and safe effective config |
| `ApplicationArguments` lacks an app property | App properties are not necessarily CLI arguments | Read via `Environment`/`@ConfigurationProperties` |
| Kubernetes Pod did not increase RAM | Used `app.*` instead of `deployer.*`, wrong platform or app name | Check deployer property and Pod spec |
| Local platform ignores Kubernetes property | Deployer does not support another platform's properties | Use the proper `deployer.<app>.local.*` namespace |
| JVM hits OOM despite large memory limit | Inappropriate Java heap/native memory settings, memory leak | Check JVM flags, container usage, GC, and logs |
| Task launched but no TaskExecution exists | JVM crashed early, DB/schema/task config error | Cross-check platform logs and TaskRepository |
| Task exits 0 but results are missing | Runner returned before async worker finished or swallowed exception | Await futures and let errors propagate |
| Two launches wrote duplicates | Missing business key/idempotency | Unique constraint, transactions, checkpoints |
| A schedule always processes the same date | Hardcoded `--date` argument | Design controlled business date resolution |
| Secret appears in task execution args | Passed secret via CLI or app property converted to CLI | Move to secret manager/environment |
| Wrong app version ran | Registry/default version differs from expectation | Specify/verify app version and image digest |
| New Batch JobInstance on every retry | Changing identifying timestamp/`run.id` | Keep identifying JobParameters stable |

### Concise Inspection Checklist

1. Read the actual **task definition** and app labels in SCDF.
2. Identify each value's source: `--arguments`, `app.*`, `deployer.*`, or `application.yml`.
3. Inspect the launch request and external execution ID without printing secrets.
4. Verify the Pod/process was created with the expected CPU/RAM and environment.
5. Read TaskExecution and application logs; for Spring Batch, also read JobExecution.
6. Reconcile business results and the idempotency key before retrying.

## 17. Step-by-Step Lab Exercise

Goal: launch `dailyclose` for two different dates, use an app property to choose output format, and use a deployer property to adjust RAM.

1. **Prepare the application:** compatible Spring Boot/Spring Cloud Task, `ApplicationRunner` parsing `--tenant`/`--date`/`--dry-run`, DataSource, and persistent TaskRepository schema.
2. **Register the `dailyclose` app** in SCDF matching your Local/Kubernetes platform; create task definition `daily-close`.
3. **First run:**

~~~text
dataflow:> task launch daily-close --arguments "--tenant=tenant-A --date=2026-11-23 --dry-run"
~~~

4. **Second run** with report format and Kubernetes memory limit:

~~~text
dataflow:> task launch daily-close --arguments "--tenant=tenant-A --date=2026-11-24" --properties "app.dailyclose.report.format=csv,deployer.dailyclose.kubernetes.limits.memory=1024Mi"
~~~

5. **Verify Spring config:** `report.format` is read by the application via Spring Environment, not assumed from `getOptionValues("report.format")`.
6. **Verify deployer:** the Pod has the expected memory limit; on the Local platform, use a matching Local property instead of Kubernetes keys.
7. **Query TaskExecution:** `task execution list --name daily-close` and `task execution status --id <ID>` using the actual ID.
8. **Test invalid input:** omit the date or pass `--date=invalid`; verify the runner raises an error and task status reflects failure.
9. **Test same-day retry:** confirm a new TaskExecution is created while business results are not duplicated.
10. **Verify security:** args and logs contain no raw passwords, tokens, or JDBC credentials.
11. **If using a Batch Job:** keep identifying JobParameters stable across retries of the same period.

| Verification Target | Expectation |
|---|---|
| Launch arguments | `tenant`, `date`, `dry-run` reach the runner |
| App property | `report.format` resolves properly in Spring Environment |
| Deployer property | Pod resources are applied on the target platform |
| TaskExecution | Records run and outcome per framework capabilities |
| Batch JobParameters | Identifying keys remain consistent if Batch is used |
| Business output | No duplicate records across repeated launches |
| Security | No secrets exposed in CLI/TaskRepository/logs |

## 18. Production Checklist and Conclusion

- **Separate the three channels:** arguments for per-run inputs; `app.*` for Spring configuration; `deployer.*` for deployment platform settings.
- **Pin versions:** app artifact/image, Data Flow, Spring Boot/Spring Cloud Task, and deployer must be compatible.
- **Use exact app labels:** especially in composed tasks and when the task definition name differs from the application name.
- **Avoid conflicting config sources:** check actual precedence based on how the launcher forwards properties.
- **Provide secure secret sources:** never pass passwords in arguments, raw properties, or JobParameters.
- **Observe both layers:** "launch accepted" is not "task completed"; monitor both TaskExecution and the Pod/process.
- **Await work completion:** the runner must not exit before business writes commit and required futures complete.
- **Have retry policies and idempotency:** the same business key is handled safely across multiple TaskExecutions.
- **Handle platform-specific failures:** timeouts, quotas, resource limits, and launch failures.
- **Schedule with explicit timezones:** never confuse the execution timestamp with the business date.

**Conclusion:** When using Spring Cloud Data Flow to launch finite Spring Cloud Task applications, distinguish **`--arguments`** (run inputs), **`app.<app>.*`** (application configuration), and **`deployer.<app>.*`** (platform configuration). This separation lets operators change processing dates, output formats, or CPU/RAM without modifying source code, while maintaining security, TaskExecution traceability, and safe retries.

### References

- [Spring Cloud Data Flow Reference — Launching a Task](https://docs.spring.io/spring-cloud-dataflow/docs/current/reference/htmlsingle/#_launching_a_task)
- [Spring Cloud Data Flow Reference — Kubernetes Deployer Properties](https://docs.spring.io/spring-cloud-dataflow/docs/current/reference/htmlsingle/#_deployer_properties_2)
- [Spring Cloud Data Flow — Composed Task: Passing Properties](https://dataflow.spring.io/docs/feature-guides/batch/composed-task/)
- [Spring Cloud Task Reference](https://docs.spring.io/spring-cloud-task/reference/)
