# Registering a Task Application and Creating a Task Definition

A **Spring Cloud Task** application is designed to perform finite-duration work: start a Spring Boot process, process data, record status to a **TaskRepository**, and then terminate. For example, an order-import application receives a data source code and a business date, reads a CSV file, updates the database, and exits with an appropriate exit code. When you want to operate this application through a UI, API, or schedule, **Spring Cloud Data Flow (SCDF)** provides a management layer to **register applications**, **create task definitions**, and **launch runs**.

This lesson belongs to the **Data Flow** chapter and focuses directly on the first two operations: **registering a Task application in the App Registry** and **creating a Task Definition from a registered application**. To understand why these two operations are needed, the lesson continues through launching, `TaskExecution` history, passing parameters, and troubleshooting errors. The examples use Spring Cloud Data Flow Shell and Dashboard, and clarify where Data Flow stores its metadata compared to the metadata written by Spring Cloud Task.

> **Ecosystem and version note:** The command-line examples are based on Spring Cloud Data Flow **2.11.x** documentation. As officially announced on **April 21, 2025**, Spring designated **2.11.x as the final open-source release line of Spring Cloud Data Flow**; subsequent releases are only provided commercially to eligible customers. Therefore, for new deployments you must check your Data Flow, Shell, Spring Boot, Spring Cloud Task, and Kubernetes/Cloud Foundry platform versions as well as actual licensing entitlements. Syntax, UI, schemas, and features may vary across versions.

## 1. Three Easily Confused Concepts

First, separate **Task application**, **Task Definition**, and **Task Execution**:

| Component | Meaning | Example | When Is It Created? |
| --- | --- | --- | --- |
| **Task application** | An artifact capable of running a finite task, such as a JAR or container image | `invoice-report-task:1.0.0` | When building/publishing the application |
| **App Registration** | A record in the **SCDF App Registry** mapping a logical name and type `task` to an artifact URI | `invoice-report → docker:registry.example.com/batch/invoice-report-task:1.0.0` | When running `app register` |
| **Task Definition** | A named definition referencing a registered Task application and optionally containing DSL configuration | `daily-invoice-report → invoice-report` | When running `task create` |
| **Task Launch** | A request to Data Flow to start a run of a Task Definition with arguments/properties | Run reporting period `2026-11-23` | When running `task launch` or clicking Launch in the UI |
| **Task Execution** | An actual run identified by an execution ID, with timestamps, exit code, and arguments | `TaskExecution ID=4101` | When the Task process executes and metadata is written |
| **Batch JobExecution** | An execution of a Spring Batch Job inside the Task, if present | `JobExecution ID=905` | When the application starts a Batch Job |

**Registering an application does not mean the application has run.** **Creating a task definition does not produce processing results yet either.** One definition can be launched multiple times with different arguments; each run creates its own execution history, provided the process starts far enough for Spring Cloud Task to write metadata.

### Full Lifecycle Diagram

~~~mermaid
flowchart TD
    A["Build and publish JAR / container image"] --> B["SCDF: app register --type task"]
    B --> C[("App Registry<br/>name + type + artifact URI")]
    C --> D["SCDF: task create"]
    D --> E[("Task Definition Repository<br/>name + DSL")]
    E --> F["SCDF: task launch / Schedule"]
    F --> G["TaskLauncher / Platform Deployer"]
    G --> H["Spring Boot + Spring Cloud Task process"]
    H --> I["Runner / Spring Batch Job / business logic"]
    H --> J[("TaskRepository<br/>TaskExecution")]
    I --> K[("Business DB or object storage")]
    I --> L["Exit code, logs, output"]
    J --> M["SCDF Task Executions / Dashboard"]
~~~

You can think of SCDF as the **control plane** for managing artifacts, definitions, and launch commands; Spring Cloud Task runs inside the **execution process** to record its lifecycle. The two layers connect, but neither replaces the other's role.

## 2. Prerequisites Before Registering

SCDF needs access to a **built and published Task application**, along with a platform on which to launch it. For a concrete environment, prepare:

1. A configured **Data Flow Server** with App Registry/Task APIs, a metadata database, and operator permissions.
2. **Data Flow Shell** connected to the right server, or use the Dashboard/REST API. Shell may require configuring the URL and credentials depending on the deployment setup.
3. An operational **Task platform** (such as Kubernetes, Cloud Foundry, or a platform supported by your SCDF version) and an account with permission to create workloads.
4. A **resolvable artifact** from the execution environment: an accessible Maven repository, HTTP(S) endpoint, or appropriate Docker registry. A URI is only useful when SCDF/the deployer can fetch the artifact.
5. A **Spring Boot application compatible with Spring Cloud Task**, with compatible dependencies/versions, a DataSource, and the TaskRepository schema if you want persistent history.
6. **Connection secrets and business resource permissions** supplied via a secret manager/platform configuration. Do not put passwords in Task Definition DSL or launch arguments.

Example of a minimal Java application using `ApplicationRunner`:

~~~java
import java.time.LocalDate;
import java.util.List;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTask
public class InvoiceReportTaskApplication {

    public static void main(String[] args) {
        SpringApplication.run(InvoiceReportTaskApplication.class, args);
    }

    @Bean
    ApplicationRunner generateReport(InvoiceReportService service) {
        return args -> {
            List<String> dates = args.getOptionValues("business-date");
            if (dates == null || dates.size() != 1
                    || dates.get(0).isBlank()) {
                throw new IllegalArgumentException(
                        "Expected --business-date=yyyy-MM-dd");
            }

            LocalDate date = LocalDate.parse(dates.get(0));
            service.generate(date); // Complete synchronously before returning.
        };
    }
}

interface InvoiceReportService {
    void generate(LocalDate businessDate);
}
~~~

This is an **illustrative skeleton**: you need a bean implementing `InvoiceReportService`, the Spring Cloud Task dependency, a JDBC driver, and a real DataSource configuration. It demonstrates two key points: the task **terminates after its work completes** and **arguments must be validated**. If `generate` fails, the application must surface the error/exit code so the orchestrator and TaskRepository record the true outcome.

Example `application.yml` for a Task application using an environment-provided database:

~~~yaml
spring:
  application:
    name: invoice-report-task
  main:
    web-application-type: none
  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}
  cloud:
    task:
      initialize-enabled: false
~~~

This example assumes **the TaskRepository schema has already been created via a compatible migration** before running; setting `initialize-enabled: false` does not create tables automatically. Especially when the application is launched by SCDF, verify that the DataSource provided to the Task actually points to the metadata store that SCDF can read.

## 3. Step A: Registering the Task Application in SCDF

Registration means **assigning a logical name to an artifact and telling SCDF the application type is `task`**. Basic command in Data Flow Shell:

~~~text
dataflow:> app register --name invoice-report --type task --uri maven://com.example.batch:invoice-report-task:1.0.0
~~~

In this example:

- `invoice-report` is the **registration name** used to reference the app in Task Definition DSL.
- `task` is the **application type**; do not use `source`, `processor`, or `sink`, which are for Stream applications.
- `maven://com.example.batch:invoice-report-task:1.0.0` is the URI to the artifact. The artifact must exist in a repository resolvable from the SCDF environment.

### 3.1. Common URI Types

| Packaging | Example URI | When Appropriate |
| --- | --- | --- |
| **Maven** | `maven://com.example.batch:invoice-report-task:1.0.0` | Server/deployer can resolve Maven artifacts |
| **Docker/OCI image** | `docker:registry.example.com/batch/invoice-report-task:1.0.0` | Container deployment on a supported platform such as Kubernetes |
| **File** | `file:///opt/task-artifacts/invoice-report-task-1.0.0.jar` | Platform can access the file path from where artifacts are resolved |
| **HTTPS** | `https://artifacts.example.com/tasks/invoice-report-task-1.0.0.jar` | Artifact is served over HTTPS with appropriate access permissions |

Not **every URI works on every Task platform**. With `file:`, the file path must be accessible to the component that actually resolves it; a file existing on your laptop does not mean a Pod can read it. With Docker, registry credentials, image pull permissions, architecture, and entrypoint must fit the platform.

**Example registering an image for Kubernetes:**

~~~text
dataflow:> app register --name invoice-report --type task --uri docker:registry.example.com/batch/invoice-report-task:1.0.0
~~~

Registering an artifact is a **metadata declaration**; it does not prove the image was pulled successfully and does not run a container. Verify resolution/pull capability through validation and a test launch in a staging/test environment.

### 3.2. Maven URI Syntax and Versions

The Maven URI syntax is described by SCDF as:

~~~text
maven://<groupId>:<artifactId>[:<extension>[:<classifier>]]:<version>
~~~

For example:

~~~text
maven://com.example.batch:invoice-report-task:1.0.0
maven://com.example.batch:invoice-report-task:jar:1.0.0
~~~

In systems requiring reproducible results, use **deterministic artifact versions** and avoid floating tags such as `latest` for critical jobs. If the same app name is re-registered or its URI is changed, check your running SCDF instance's version/registration policy and its impact on existing definitions.

**An app registration name is not a business key.** One `invoice-report` application can run for many dates or tenants; the registration name identifies the **artifact type**, not a **specific report release run**.

### 3.3. Registering via the Dashboard

In the SCDF Dashboard, the usual workflow is:

1. Open **Applications/Apps**, then select the option to add or register applications.
2. Choose **Register one or more applications**, type **Task**.
3. Enter the name `invoice-report` and the Maven/Docker URI of the published artifact.
4. Save/import the registration and verify it appears in the App Registry.

Button labels can vary across UI versions. What you must verify afterward is that the **name**, **task type**, and **URI/version** match the artifact you intend to use; do not rely solely on a status badge color in the UI.

## 4. Step B: Creating a Task Definition from a Registered Application

After registering `invoice-report`, create **a uniquely named task definition**:

~~~text
dataflow:> task create daily-invoice-report --definition "invoice-report"
~~~

The command above has two parts with different roles:

| Value | Meaning |
| --- | --- |
| `daily-invoice-report` | **Task Definition name** in SCDF |
| `invoice-report` | Name of the **registered Task application** in the App Registry |
| `--definition "invoice-report"` | DSL describing the component/program to run |

The same app registration can be used to create multiple Task Definitions:

~~~text
dataflow:> task create daily-invoice-report --definition "invoice-report"
dataflow:> task create month-end-invoice-report --definition "invoice-report"
~~~

Both definitions point to the same logical artifact, but **they are managed and invoked independently by two different names**. In real operations, use multiple definitions when they have different schedules, owners, environments, or purposes. If the goal is simply to rerun for another date, **one definition can be launched multiple times with different date arguments** without creating a new definition for every day.

### 4.1. Task Definition DSL

Illustrative syntax in SCDF documentation:

~~~text
dataflow:> task create format-year-demo --definition "timestamp --format=\"yyyy\""
~~~

This is **Data Flow** DSL, where `timestamp` is a registered application name and `--format` is an application property in the definition. For this lesson, prefer the minimal definition `"invoice-report"`, and pass the business date at launch time so it stays reusable.

A **Composed Task Definition** can chain multiple Task applications using DSL such as:

~~~text
taskA && taskB
~~~

SCDF uses **Composed Task Runner** to orchestrate the components when running a composed task. That is an extended topic; while learning single-app registration and definition creation, just understand that a single task's DSL can simply be **one app name**, without connecting START/END symbols in the Shell.

### 4.2. Creating a Task Definition via the Dashboard

In the UI:

1. Open **Tasks** and select **Create Task**.
2. Pick the `invoice-report` app from the palette or enter the definition `invoice-report`.
3. In the canvas editor, connect **START → invoice-report → END**.
4. Select Create and name it `daily-invoice-report`.
5. Verify the Task Definitions list shows the definition with the expected name and DSL.

**Creating the definition does not run the job yet.** The Dashboard may show no executions or `UNKNOWN` for a new definition; this is not evidence that the Job failed.

### 4.3. Checking the Definition with the Shell

After creating it:

~~~text
dataflow:> task list
dataflow:> task validate daily-invoice-report
~~~

`task list` lists the created Task Definitions. `task validate` checks whether the referenced application still has a valid URI according to the server's resolution capability; **validation does not replace an actual launch** on Kubernetes/Cloud Foundry, database permission checks, or business verification.

**Definition names are subject to platform limits.** For example, Kubernetes restricts resource name length; avoid spaces, special characters, or overly long names. Choose short, stable, descriptive names such as `daily-invoice-report`.

## 5. Step C: Launching the Definition and Passing Arguments

Once the definition is created, you can launch it via Shell:

~~~text
dataflow:> task launch daily-invoice-report --arguments "--business-date=2026-11-23"
~~~

SCDF requires the **definition name**, not the Maven artifact name. Each launch is a new run request; if the process starts and TaskRepository writes metadata normally, a new TaskExecution is created.

Assuming the runner reads the `business-date` parameter using `ApplicationArguments` as in Section 2, `--business-date=2026-11-23` is passed as an **application argument**, parsed into a `LocalDate`, and used to determine the report data.

### 5.1. Distinguishing Arguments and Properties

SCDF Shell has two easily confused options:

| Option on `task launch` | Example | Meaning |
| --- | --- | --- |
| `--arguments` | `"--business-date=2026-11-23"` | Command-line arguments intended for the **Task application** |
| `--properties` | `"app.daily-invoice-report.example=value"` | Properties forwarded to **TaskLauncher** or the application/deployer depending on prefix and deployment setup |

General example from SCDF documentation:

~~~text
dataflow:> task launch daily-invoice-report --arguments "--business-date=2026-11-23 --dry-run=true"
~~~

In `--properties`, the prefix **`app.<task-definition-name>.<property>`** is used for application properties and **`deployer.<task-definition-name>.<property>`** is used for deployment properties; exact property names and how the launcher injects them into the container depend on the platform.

Do not pass `--business-date` inside `--properties` and assume `ApplicationArguments` will see it like a command-line argument. If the job expects `ApplicationArguments.getOptionValues("business-date")`, use **`--arguments`** or intentionally update the application to read configuration through `Environment`.

### 5.2. Launching from the Dashboard

Under **Tasks → Task Definitions**, select `daily-invoice-report` and then **Launch**. The UI usually provides separate fields for:

- **Arguments:** `--business-date=2026-11-23`.
- **Properties:** application/deployer properties according to how SCDF passes them to TaskLauncher.
- **Platform:** target account/platform when the server is configured with multiple options.

After submitting the request, the UI may navigate to the executions list page. A successful response from the **Launch** button only indicates **the run request was accepted**; actual business results must be checked in the execution record, logs, and target data store.

### 5.3. Launching Multiple Times

~~~text
dataflow:> task launch daily-invoice-report --arguments "--business-date=2026-11-23"
dataflow:> task launch daily-invoice-report --arguments "--business-date=2026-11-24"
~~~

Both commands use **one Task Definition** but different business data. SCDF does not automatically guarantee that a reporting period runs only once. For results that must be **idempotent**, the application needs a business key such as `(tenantId, businessDate, reportVersion)`, source validation, and clear output write rules.

If the application integrates Spring Batch, distinguish **Task arguments** from **Spring Batch JobParameters**; mapping between the two parameter sets must be handled by the launcher or application according to your version.

## 6. Where Definitions Live vs. Where Execution State Lives

When using SCDF, there are at least three data layers to distinguish:

~~~mermaid
flowchart LR
    U["User / SCDF Shell"] --> A["Data Flow Server"]
    A --> AR[("App Registry<br/>name, type, URI")]
    A --> TD[("Task Definition store<br/>name, DSL")]
    A --> P["TaskLauncher / Platform"]
    P --> X["Task application process"]
    X --> TR[("TaskRepository<br/>TaskExecution + args")]
    X --> BR[("Business DB<br/>data and results")]
    A -. "reads executions from matching datastore" .-> TR
~~~

| Data Store | Primary Contents | Who Creates/Updates It? |
| --- | --- | --- |
| **SCDF App Registry** | `task.invoice-report → artifact URI/version` | SCDF on app register/unregister |
| **SCDF Task Definition Repository** | `daily-invoice-report → invoice-report` | SCDF on definition create/destroy |
| **Spring Cloud TaskRepository** | `TaskExecution ID`, task name, start/end, exit code, exit message, arguments | Task application through the Spring Cloud Task lifecycle |
| **Spring Batch JobRepository** (if present) | JobInstance, JobExecution, StepExecution, checkpoints | Spring Batch when running a Job |
| **Business DB** | Reports, imported records, source status, checksums | Business logic |

SCDF may use a database to store both control metadata and execution metadata, but **do not conflate the different record types**. A Task Definition is a **runnable template**, whereas a TaskExecution is the **history of a single run**.

### 6.1. Conditions for SCDF to See TaskExecution

In the traditional SCDF model, when SCDF launches a Task, it supplies the application with the datasource properties needed for **the Task to write metadata to a repository that Data Flow can read**. This requires:

1. The application includes a JDBC driver matching the database (for example, PostgreSQL if Data Flow uses PostgreSQL).
2. The datasource, connection details, permissions, and TaskRepository schema are **for the right environment** and compatible with Spring Boot/Spring Cloud Task.
3. Data Flow Server has permission to read Task metadata in that datastore; if multiple schema/version targets exist, the right lookup target must be configured.
4. You do not accidentally override the application's datasource to a private in-memory H2 database or a different store, causing executions to "vanish" from the Dashboard.

**If a Task is launched outside SCDF**, it can still be tracked by SCDF if it writes metadata to the datastore used by SCDF and meets the configuration requirements; however, this does not happen automatically just because the application name matches.

**Do not put secrets in Task arguments:** Spring Cloud Task can persist arguments into `TASK_EXECUTION_PARAMS`, in addition to logs and command history. Database connections should use platform-provided secrets/configuration, never passwords embedded in `--arguments`.

## 7. Viewing TaskExecution History After Launching

In Data Flow Shell, the inspection commands documented are:

~~~text
dataflow:> task execution list
dataflow:> task execution list --name daily-invoice-report
dataflow:> task execution status --id 4101
~~~

`4101` is a **hypothetical ID** for illustration; replace it with an actual ID from `task execution list`. Displayed status can include task name, start/end timestamps, exit code, exit message, and run arguments.

| Observation | Reasonable Interpretation |
| --- | --- |
| New execution ID exists, no end time yet | Task may still be running or did not record completion; cross-check Pod/Job |
| `EXIT_CODE=0`, end time present | Process exited technically successfully; still verify business outcomes |
| `EXIT_CODE` non-zero | Task reported an error; read logs and exception details |
| Launch accepted but no execution appears | Check TaskLauncher, image pull, startup failure, datasource/schema, and platform logs |
| Execution from standalone run is missing | Check shared TaskRepository, connection, schema target, and read permissions |
| One definition has multiple executions | Normal: one definition launched multiple times |

In the Dashboard, go to **Tasks → Task Executions** and select an execution ID to view details. When Spring Batch is integrated, the UI may also provide links to the corresponding JobExecution.

### 7.1. Distinguishing a Successful Launch from a Successful Task

~~~text
Task Definition: daily-invoice-report
    │
    ├─ Launch #1: --business-date=2026-11-23
    │      └─ TaskExecution 4101: COMPLETED / exitCode=0
    │
    ├─ Launch #2: --business-date=2026-11-24
    │      └─ TaskExecution 4102: FAILED / exitCode!=0
    │
    └─ Launch #3: --business-date=2026-11-24
           └─ TaskExecution 4103: COMPLETED / exitCode=0
~~~

This is only an **illustrative scenario**. Having SCDF accept a launch does not mean the Task ran successfully; a TaskExecution ID is also distinct from an orchestrator request ID. When a failure occurs, rerunning with the same business parameters must be designed not to create duplicate data.

## 8. When Do You Need a Schedule or Composed Task?

Registration and definition creation are **preparation steps**; a task only runs when a launch request or a configured schedule triggers it. SCDF provides **Task Scheduling** on supported platforms/versions when the feature is enabled.

Example syntax in Data Flow Shell 2.11.x:

~~~text
dataflow:> task schedule create --definitionName daily-invoice-report --name daily-invoice-schedule --expression "0 2 * * *"
~~~

This schedule is illustrative only; expression syntax accuracy, timezone, Cron parser, and scheduler limits must be verified against the configured platform. Scheduling features may be **disabled by default** and require enabling via server configuration, such as `spring.cloud.dataflow.features.schedules-enabled` and `spring.cloud.dataflow.features.tasks-enabled` on supported versions.

**A task definition is not a schedule definition.** A Task Definition can be run ad hoc or across many different requests. If you need to run `import → validate → report` with success/failure branches, study **Composed Task Runner** instead of assuming a single Task definition orchestrates a multi-step workflow on its own.

## 9. Managing Changes to Artifacts and Task Definitions

Several common scenarios:

| Change | What to Check |
| --- | --- |
| Pushing image `invoice-report-task:1.0.1` | Is the new version published and pullable? Does the SCDF App Registry still point to the old version? |
| Changing a registration URI | Which Task Definitions depend on that app name? How will SCDF/deployer select the artifact on the next launch? |
| Renaming runner parameter `business-date` to `report-date` | Are existing schedules and launch requests still valid? |
| Changing TaskRepository DataSource/schema | Will old executions still appear in SCDF, and is there a migration plan? |
| Deleting a Task Definition | `task destroy` removes the definition; assess impact on schedules and execution data |
| Increasing concurrent runs | Add workload limits, database capacity, and business-key idempotency |

**Distinguish `app unregister` and `task destroy`:** unregister applies to the artifact registration record, whereas destroy applies to the task definition. In SCDF documentation, `task destroy <name>` does not delete existing TaskExecution history by default; certain cleanup modes may alter this behavior. Do not delete definitions merely to "rename" them while production schedules depend on them.

Well-run teams manage **image/JAR versions**, **task definitions**, **deployment configurations**, and **schedules** as change-controlled artifacts. When old reports must be traceable, retain enough information on artifact version, business key, and source checksum to reproduce results.

## 10. Troubleshooting Common Errors

| Symptom | Causes to Consider | First Check |
| --- | --- | --- |
| `task create` reports app not found | Not registered yet, or wrong app name/type | Verify App Registry contains `task.invoice-report` |
| Registration succeeded but launch does not run | Unresolvable artifact URI, registry credentials, image pull failure | `task validate`, TaskLauncher/Pod/Job logs |
| Image starts but application does not exit | Runner spawned background threads or a web server | `spring.main.web-application-type=none`, await Future/Job completion |
| Launch missing `business-date` | Forgot `--arguments`, misspelled option name | Inspect launch request/Task args and runner validation |
| Task has exit code 0 even though report failed | Exception swallowed or Batch Job FAILED not reflected to Task | Handle errors explicitly; check JobExecution/exit codes |
| `TaskExecution` missing from SCDF | Task DataSource differs from SCDF datastore, wrong schema, or early startup crash | Compare connections, drivers, permissions, schema targets, and logs |
| UI shows Task Definition but no executions | Definition created only, never launched | Click Launch or configure a schedule |
| Re-running same date produces duplicate report | No business idempotency | Unique key/report version, upsert, and outbox for notifications |
| Logs not visible | Logs kept on platform or short retention | Check Pod logs, logging backend, and view permissions |
| Scheduler does not create runs | Schedule feature disabled, unsupported platform, wrong Cron/timezone | Server feature flags, scheduler logs, and manual launch test |

**Effective investigation approach:** identify whether the failure occurred at **registration**, **definition**, **launch/platform**, **TaskRepository startup**, or **business logic**. A successful `app register` command only confirms SCDF stored the registration metadata; it does not prove the four subsequent stages will succeed.

## 11. End-to-End Hands-On Walkthrough

Assume a data import application `csv-import-task` is already built, can run standalone, and has an image with a fixed tag `1.0.0`.

### 11.1. Register, Define, and Launch

In SCDF Shell:

~~~text
dataflow:> app register --name csv-import --type task --uri docker:registry.example.com/batch/csv-import-task:1.0.0

dataflow:> task create daily-csv-import --definition "csv-import"

dataflow:> task list

dataflow:> task validate daily-csv-import

dataflow:> task launch daily-csv-import --arguments "--source-id=partner-A-2026-11-23 --business-date=2026-11-23"
~~~

This is an **example**, not runnable directly from the documentation; the Docker registry and image must be replaced with resources accessible to your SCDF environment. If your application lacks `--source-id` and `--business-date` options, adjust the runner first.

### 11.2. Observe and Rerun

~~~text
dataflow:> task execution list --name daily-csv-import

dataflow:> task execution status --id 4101
~~~

Record the results:

| Item | Result to Record |
| --- | --- |
| App registration | Type `task`, URI, version |
| Task Definition | `daily-csv-import`, DSL `csv-import` |
| Launch arguments | `source-id`, `business-date` |
| TaskExecution | ID, start/end, exit code, exit message |
| Business result | Total imported rows, error count, checksum |
| Rerun evidence | Running the same source ID twice does not duplicate records |

After the first run, try **rerunning with the same arguments** and verify idempotency in the business table. Each technical run can generate its own TaskExecution ID; do not treat that as a signal that new data was imported.

### 11.3. Test Important Failure Cases

1. **Invalid URI:** register a non-existent image in a test environment, run `task validate`, then attempt a launch to observe resolver/deployer errors.
2. **Missing argument:** launch without `--business-date`; confirm the runner throws an error and produces an appropriate exit code.
3. **Wrong DataSource:** point the Task to a different repository, then explain why SCDF cannot see that execution.
4. **Duplicate source processing:** invoke the same `source-id` twice; verify the unique key and row counts after import.
5. **New image version:** register a new version following your supported workflow and confirm the definition/runs use the intended artifact.

**Completion criteria:** the learner can explain verbally and demonstrate through test results **register app → create definition → launch → view execution**; knows which records SCDF manages versus which records Spring Cloud Task writes; and can diagnose why "I clicked Launch but the Task isn't running."

## 12. Key Takeaways

1. **`app register --type task`** maps a Task application's logical name to an artifact URI; this step **does not run** the application yet.
2. **`task create <name> --definition "<app-name>"`** creates a reusable Task Definition. The definition name and the registered app name are **two independent names**.
3. **`task launch <definition-name>`** creates a run request. **`--arguments`** passes arguments to the application, while **`--properties`** belongs to the TaskLauncher/deployer mechanism.
4. **TaskDefinition differs from TaskExecution**: one definition can produce many executions; each run should be reconciled via start/end times, exit code, and business outcome.
5. SCDF manages **registry, definitions, launches, schedules, and observation UI**; Spring Cloud Task manages **lifecycle and `TaskExecution` metadata**; Spring Batch (if used) manages **Job/Step metadata**.
6. For SCDF to see history, **TaskRepository and DataSource/schema configurations must align**, even when the launcher and Task run in different processes.
7. Registering and creating definitions **do not replace** validation, logging, secrets management, idempotency, concurrency control, and artifact version governance.

### References

- [Spring Cloud Data Flow Reference Guide 2.11.x — Lifecycle of a Task](https://docs.spring.io/spring-cloud-dataflow/docs/2.11.3/reference/htmlsingle/#_the_lifecycle_of_a_task)
- [Spring Cloud Data Flow — Getting Started with Task Processing](https://dataflow.spring.io/docs/batch-developer-guides/getting-started/task/)
- [Spring Cloud Data Flow — Deploying a Spring Cloud Task application](https://dataflow.spring.io/docs/batch-developer-guides/batch/data-flow-simple-task/)
- [Spring Cloud Data Flow — Short-lived Applications](https://dataflow.spring.io/docs/concepts/architecture/)
- [Spring Cloud Data Flow — Tooling](https://dataflow.spring.io/docs/concepts/tooling/)
- [Spring Blog — End of Open-Source (April 21, 2025)](https://spring.io/blog/2025/04/21/spring-cloud-data-flow-commercial/)
