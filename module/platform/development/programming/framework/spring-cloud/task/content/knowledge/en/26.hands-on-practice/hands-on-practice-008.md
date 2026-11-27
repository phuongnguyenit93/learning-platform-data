# Deploying a Kubernetes Job or CronJob and Observing Results

## 1. Objectives of This Practice Lab

In **Spring Cloud Task**, a Spring Boot application is designed to run for a finite duration, perform its work, and terminate. Spring Cloud Task records each execution as a `TaskExecution` in `TaskRepository`: ID, task name, start/end timestamps, exit code, and parameters. Kubernetes offers two workload types suited for deploying it:

- **Job**: instructs Kubernetes to run a workload until completion or failure criteria are met.
- **CronJob**: instructs Kubernetes to **create Jobs** on a schedule; a CronJob does not execute Java code directly.

This lab builds a `daily-close-task` application simulating daily revenue closing per tenant and business date, packages it into a container image, runs it once as a Job, and configures daily execution via CronJob. Every run must inspect **three layers of outcomes**: Kubernetes, Spring Cloud Task, and actual persisted business data.

After this lesson, learners will be able to:

1. Write an `ApplicationRunner` that starts no web server and returns appropriate exit codes.
2. Prepare PostgreSQL for `TaskRepository` and a result table with an idempotency key.
3. Package a JAR into a Docker image and pass configuration via environment variables/Secrets.
4. Define a Job or CronJob with a `batch/v1` manifest, configuring deadlines, retries, quotas, and schedules.
5. Use `kubectl` to inspect Jobs, Pods, logs, exit codes, and failure causes.
6. Correlate `TaskExecution` with business output to distinguish **successful launch**, **successful process exit**, and **committed business work**.
7. Rehearse retries after commit, proving no duplicate data is written.
8. Understand the limits of `concurrencyPolicy: Forbid`, `backoffLimit`, and automatic Job cleanup.

This is a **guided lab**. The code blocks describe files and commands for **the learner's own practice project**; this guide does not deploy to a live cluster or create real Secrets.

## 2. Overall Architecture and Three Status Sources

~~~mermaid
flowchart TD
    U["Operator / CronJob Controller"] --> J["Kubernetes Job"]
    J --> P["Pod running task container"]
    P --> A["Spring Boot + Spring Cloud Task"]
    A --> R["ApplicationRunner"]
    R --> S["DailyCloseService"]
    A --> TR["PostgreSQL: TaskRepository"]
    S --> BD["PostgreSQL: daily_close_result"]
    P --> L["Pod status + container exit code + logs"]
    J --> K["Job conditions Complete / Failed"]
    TR --> Q["Query TaskExecution"]
    BD --> Q
    K --> Q
    L --> Q
~~~

Three sources of truth must be checked independently:

| Source | Questions to Answer | What Is Still Not Guaranteed |
|---|---|---|
| Kubernetes Job / Pod | Did the container run, what exit code did it return, did it retry or get OOMKilled? | That business data is guaranteed correct |
| Spring Cloud `TaskRepository` | How many `TaskExecution`s exist, and what were each run's timestamps and exit code? | That external side effects ran exactly once |
| Business result table | Does the right result exist for tenant/date/revision without duplicates? | That downstream APIs/brokers received events if any were called |

For example, a worker might **commit data and then be killed** before `TaskRepository` receives its final status update. Kubernetes reports Pod Failed and `TaskExecution` may lack `END_TIME`, yet the business table already holds the row. Without idempotency on retries, duplicate results would be created.

That is why this lab intentionally gives `daily_close_result` a **primary key based on the business key**, rather than using `taskExecutionId` as the business key.

## 3. Choosing Kubernetes Job or CronJob?

| Requirement | Recommendation | Reason |
|---|---|---|
| Backfill a specific date | **Job** | Pass fixed `--date=yyyy-MM-dd` and control a single run |
| Run daily at 02:00 | **CronJob** | Automatically spawns Jobs per schedule and declared timezone |
| API receives requests and spawns tasks | Job via Kubernetes API or a task launcher | One finite workload per request |
| Web server must stay up 24/7 | Deployment / dedicated service | Not a finite-task workload |
| Splitting across thousands of partitions | Spring Batch/remote partitioning or Indexed Job as appropriate | Requires dedicated concurrency/checkpoint design |

For finite tasks, **never use a Deployment just to run an `ApplicationRunner` once and exit**. The Deployment controller tries to keep replicas running and will restart exited containers, repeating work.

Kubernetes Jobs also **do not guarantee exactly-once execution**: even with `parallelism: 1`, `completions: 1`, and `restartPolicy: Never`, Kubernetes documentation warns that a program may start more than once in certain failure scenarios. Idempotent design is mandatory.

## 4. Prerequisites

The lab requires:

- A JDK compatible with your Spring Boot version; this example uses **Java 17** and the Spring Boot 3.5 stack.
- Gradle or Maven; the build snippets below use **Gradle Groovy DSL**.
- Docker or an equivalent OCI image builder, with push access to a registry pullable by your cluster.
- A Kubernetes cluster supporting `batch/v1` and `CronJob.spec.timeZone` (stable since Kubernetes v1.27).
- `kubectl` configured with permissions in a test namespace.
- PostgreSQL reachable from Pods, initialized with the Spring Cloud Task `TaskRepository` schema for your exact version.
- A secure Kubernetes Secret supplying JDBC URL, username, and password.
- Permissions to create `Job`/`CronJob` objects in the namespace and inspect Pods/logs/statuses.

No dedicated cluster? You can use local Kubernetes such as kind, minikube, or an organizational staging environment. However, registry access, PostgreSQL networking, and Secrets must be set up accordingly; **never assume containers can reach `localhost:5432` on your dev machine**.

To scope your workspace:

~~~bash
kubectl create namespace task-lab
kubectl config current-context
kubectl get nodes
kubectl -n task-lab get jobs
~~~

Verify `current-context` **before** creating resources so you do not accidentally target a production cluster. If the namespace already exists, skip creating it.

## 5. Choosing a Compatible Spring Boot and Spring Cloud Pair

An **illustrative published Spring pairing** is:

| Component | Version Used in Example | Notes |
|---|---|---|
| Spring Boot | `3.5.13` | Boot version that Spring Cloud 2025.0.2 builds upon |
| Spring Cloud BOM | `2025.0.2` | Spring Cloud Northfields |
| Spring Cloud Task | Managed by BOM | **Do not** pin an arbitrary version |
| Java | 17 | Verify target stack requirements |
| PostgreSQL driver | Managed by Boot BOM | Avoid hardcoding unnecessarily |

This pairing keeps the lab snippets consistent, **not a recommendation to pick older releases for 2026 production systems**. For new systems, choose a currently supported release train from the official matrix and align Boot/Cloud together—for example, a Boot 4.x/Cloud 2026.x line with matching APIs. Never pair Boot 4.x with Cloud 2025.0.x just to pull one newer artifact.

References: [Spring Cloud release compatibility](https://spring.io/projects/spring-cloud/) and [Spring Cloud 2025.0.2 announcement](https://spring.io/blog/2026/04/02/spring-cloud-2025-0-2-aka-northfields-has-been-released/).

## 6. Creating the Project and Declaring Dependencies

Learning project layout:

~~~text
daily-close-task/
├── build.gradle
├── settings.gradle
├── Dockerfile
└── src/main/
    ├── java/example/task/
    │   ├── DailyCloseTaskApplication.java
    │   └── DailyCloseService.java
    └── resources/
        └── application.yml

# Kubernetes manifests will be described in later steps.
~~~

Example `settings.gradle`:

~~~groovy
rootProject.name = 'daily-close-task'
~~~

Example `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencyManagement {
    imports {
        mavenBom 'org.springframework.cloud:spring-cloud-dependencies:2025.0.2'
    }
}

dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-task'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('bootJar') {
    archiveFileName = 'app.jar'
}
~~~

Omit `spring-boot-starter-web` because the task needs no inbound HTTP server. `spring-boot-starter-jdbc` provides `JdbcTemplate` and PostgreSQL transactions; the Task starter manages the `TaskExecution` lifecycle. A real build also needs a compatible Gradle wrapper and appropriate tests.

If an application uses Spring Batch, add the version-matched Batch starter and design `Job`/`Step`/`JobRepository` separately. This lab intentionally uses **Spring Cloud Task + JDBC** to focus clearly on Kubernetes Jobs/CronJobs first.

## 7. Configuring a Non-Web Task and TaskRepository

`src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: daily-close-task

  main:
    web-application-type: none

  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}
    hikari:
      maximum-pool-size: 3

  cloud:
    task:
      name: daily-close-task
      initialize-enabled: false

logging:
  level:
    root: INFO
~~~

Here:

- `web-application-type: none` prevents Spring Boot from starting an embedded HTTP server.
- `TASK_DB_URL`, `TASK_DB_USER`, and `TASK_DB_PASSWORD` come from environment variables/Secrets at deploy time.
- `initialize-enabled: false` assumes **`TaskRepository` tables are already migrated**; the runtime JVM does not execute DDL.
- A small pool fits a short-lived task; when many Pods run concurrently, aggregate DB connections can still grow large.

**Separating schema migrations from task runtime** ensures Pod DB credentials only need DML, never `CREATE TABLE` or `ALTER TABLE`.

## 8. Creating the Business Result Table with an Idempotency Key

This table belongs to a **project-managed schema**, not Spring Cloud Task's built-in tables:

~~~sql
CREATE SCHEMA IF NOT EXISTS finance;

CREATE TABLE IF NOT EXISTS finance.daily_close_result (
    tenant_id      VARCHAR(64) NOT NULL,
    business_date  DATE NOT NULL,
    revision       INTEGER NOT NULL,
    total_amount   NUMERIC(19, 2) NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (tenant_id, business_date, revision)
);
~~~

Before running the task, create the **Spring Cloud Task PostgreSQL metadata schema** using DDL from your exact Spring Cloud Task artifact/documentation. Common tables include `TASK_EXECUTION`, `TASK_EXECUTION_PARAMS`, ID generators, and extra tables if corresponding features are enabled. Never use H2 DDL on PostgreSQL.

For production environments:

1. A `task_migrator` role creates both `TaskRepository` and business tables.
2. A `task_runtime` role receives only `USAGE` on relevant schemas and `SELECT/INSERT/UPDATE` on required tables, plus appropriate ID sequence/table grants.
3. The namespace Secret stores the connection URL and credentials of the **runtime role**, not the migrator.
4. `TaskRepository` tables must match the `tablePrefix` and search path used at runtime.

Example SQL granting permissions on the business table:

~~~sql
GRANT USAGE ON SCHEMA finance TO task_runtime;

GRANT SELECT, INSERT
ON TABLE finance.daily_close_result
TO task_runtime;
~~~

This is not the complete grant list for `TaskRepository`; also grant privileges on metadata tables/sequences matching your actual DDL. If migration and runtime target separate databases, design multi-DataSource/`TaskConfigurer` configuration explicitly rather than assuming one DataSource covers all repositories.

## 9. Writing a Finite ApplicationRunner with Post-Commit Fault Simulation

`DailyCloseTaskApplication.java`:

~~~java
package example.task;

import java.time.LocalDate;
import java.time.ZoneId;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTask
public class DailyCloseTaskApplication {

    private static final Logger log =
        LoggerFactory.getLogger(DailyCloseTaskApplication.class);

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
            SpringApplication.run(DailyCloseTaskApplication.class, args);

        int code = SpringApplication.exit(context);
        System.exit(code);
    }

    @Bean
    ApplicationRunner dailyCloseRunner(DailyCloseService service) {
        return args -> {
            String tenant = required(args, "tenant");
            String revisionValue = optional(args, "revision", "1");
            int revision = Integer.parseInt(revisionValue);

            String dateArgument = optional(args, "date", null);
            boolean previousDay = args.containsOption("previous-day");

            if ((dateArgument == null) == (!previousDay)) {
                throw new IllegalArgumentException(
                    "Use exactly one: --date=yyyy-MM-dd OR --previous-day");
            }

            LocalDate businessDate =
                dateArgument != null
                    ? LocalDate.parse(dateArgument)
                    : LocalDate.now(ZoneId.of("Asia/Ho_Chi_Minh"))
                        .minusDays(1);

            boolean inserted =
                service.closeDay(tenant, businessDate, revision);

            log.info(
                "daily-close tenant={} businessDate={} revision={} result={}",
                tenant, businessDate, revision,
                inserted ? "APPLIED" : "ALREADY_APPLIED");

            // Lab only: simulates failure after COMMIT.
            if (args.containsOption("fail-after-commit")) {
                throw new IllegalStateException(
                    "Simulated failure after business commit");
            }
        };
    }

    private static String required(
            ApplicationArguments args, String key) {
        String value = optional(args, key, null);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Missing required --" + key + "=...");
        }
        return value;
    }

    private static String optional(
            ApplicationArguments args,
            String key,
            String fallback) {

        List<String> values = args.getOptionValues(key);
        if (values == null) {
            return fallback;
        }

        if (values.size() != 1 || values.get(0) == null) {
            throw new IllegalArgumentException(
                "Expected one value for --" + key);
        }

        return values.get(0);
    }
}
~~~

**Important explanations:**

- Pass either `--date` **or** `--previous-day` on a given run, never both.
- `--date` suits backfill Jobs. `--previous-day` fits the routine CronJob example.
- The timezone is specified **directly in Java** when computing the previous day. `CronJob.spec.timeZone` only governs the Cron schedule timezone; it does not change the JVM's timezone.
- `DailyCloseService.closeDay(...)` must be a synchronous call whose transaction commits before the runner returns.
- `fail-after-commit` intentionally throws **after the service commits** to test retry safety.
- Never swallow exceptions. When a runner fails during startup, `SpringApplication.run(...)` throws before returning a context; Spring Boot handles failure/exit code per its lifecycle. Always check Pod exit codes on a real cluster.
- `SpringApplication.exit(context)` plus `System.exit(code)` on the success path exits the JVM with an explicit code after runners finish. Never call `System.exit(0)` inside a service.

### Note on Boolean Option Values

In this example, `containsOption("fail-after-commit")` and `containsOption("previous-day")` check for **option presence**. Consequently, **`--fail-after-commit=false` is still treated as enabled**. To disable it, **omit the option completely**. If production code needs explicit `true`/`false` values, parse and validate them via `getOptionValues(...)`.

## 10. Writing the Service with Transactions and a Unique Key

`DailyCloseService.java`:

~~~java
package example.task;

import java.math.BigDecimal;
import java.sql.Date;
import java.time.LocalDate;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DailyCloseService {

    private final JdbcTemplate jdbc;

    public DailyCloseService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean closeDay(
            String tenant, LocalDate businessDate, int revision) {

        int inserted = jdbc.update(
            """
            INSERT INTO finance.daily_close_result
                (tenant_id, business_date, revision, total_amount)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (tenant_id, business_date, revision)
            DO NOTHING
            """,
            tenant,
            Date.valueOf(businessDate),
            revision,
            new BigDecimal("123.45")
        );

        return inserted == 1;
    }
}
~~~

`123.45` is a **dummy test value**, not a real revenue-closing formula. In real projects, the service reads source data at a snapshot/cutoff, aggregates, validates, and commits consistently. When the same business key already exists, `ON CONFLICT DO NOTHING` prevents retries from inserting a second row.

### Why Is a Database Unique Constraint Essential?

~~~mermaid
sequenceDiagram
    participant J as Job Pod A
    participant K as Job Pod B (retry/duplicate)
    participant DB as PostgreSQL
    J->>DB: INSERT tenant-A, date=23, revision=1
    DB-->>J: 1 row inserted / committed
    J--xJ: JVM fails after commit
    K->>DB: INSERT same business key
    DB-->>K: ON CONFLICT DO NOTHING (0 rows)
    K-->>K: ALREADY_APPLIED, no duplicate write
~~~

Kubernetes can create replacement Pods or even spawn duplicate Pods during certain failure windows. A `SELECT` pre-check followed by `INSERT` is **not enough** against races without a unique constraint/transaction; two Pods can both read "not found". A database unique index is the final line of defense.

**Demo limitation:** if a retry uses the same key while source data or total amounts have changed, silently ignoring conflicts can mask inconsistencies. Production needs fingerprints/snapshots, revisions, or explicit `CONFLICT` responses. If side effects hit external APIs or message brokers, apply target-side idempotency keys or a transactional outbox.

## 11. Packaging the JAR into an OCI Image

Using the project's Gradle wrapper:

~~~bash
./gradlew clean bootJar
~~~

The build is configured to output `build/libs/app.jar`.

Example `Dockerfile`:

~~~dockerfile
FROM eclipse-temurin:17-jre

WORKDIR /app
COPY build/libs/app.jar /app/app.jar

USER 10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

This image exposes no HTTP port; `EXPOSE 8080` is unnecessary. For finite workloads, **exec-form `ENTRYPOINT`** ensures the JVM receives signals directly. Avoid shell wrappers that background Java without waiting or forwarding signals.

Build and push the test image:

~~~bash
docker build -t registry.example.org/training/daily-close-task:1.0.0 .
docker push registry.example.org/training/daily-close-task:1.0.0
~~~

`registry.example.org` is an **illustrative address**: replace it with a real registry and ensure the cluster has pull credentials. In production, prefer immutable tags or **image digests**, scan for vulnerabilities, use supported base images, and verify node CPU architecture.

## 12. Preparing Namespace, Secret, and Database Privileges

The manifests below assume:

- Namespace `task-lab` exists.
- PostgreSQL already has the Spring Cloud Task metadata schema and `finance.daily_close_result`.
- Kubernetes Secret `daily-close-db` exists **in the same namespace**, holding three keys: `url`, `username`, and `password`.
- The runtime DB role has full DML on `TaskRepository` and `SELECT/INSERT` on the business table.
- NetworkPolicies, DNS, and firewalls allow Pods to reach PostgreSQL.

Verify the Secret exists without printing its contents:

~~~bash
kubectl -n task-lab get secret daily-close-db
kubectl -n task-lab get serviceaccounts
~~~

Never put real passwords in sample manifests, never pass `--password=...` in args, and never dump full environments or base64 Secrets to terminals/logs. Practical production solutions include External Secrets Operator, Secrets Store CSI Driver, or your platform's secret manager.

**Use `automountServiceAccountToken: false`** when the task does not call the Kubernetes API. Operators and monitoring systems need permissions to inspect Jobs/Pods/logs—task Pods themselves rarely do.

## 13. Kubernetes Job Manifest for a Specific Date

Example basic `job.yaml` manifest:

~~~yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: daily-close-20261123
  namespace: task-lab
  labels:
    app: daily-close-task
    exercise: manual
spec:
  completions: 1
  parallelism: 1
  backoffLimit: 2
  activeDeadlineSeconds: 900
  ttlSecondsAfterFinished: 86400

  template:
    metadata:
      labels:
        app: daily-close-task
    spec:
      restartPolicy: Never
      terminationGracePeriodSeconds: 30
      automountServiceAccountToken: false

      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        seccompProfile:
          type: RuntimeDefault

      containers:
        - name: daily-close
          image: registry.example.org/training/daily-close-task:1.0.0
          imagePullPolicy: IfNotPresent
          args:
            - "--tenant=tenant-A"
            - "--date=2026-11-23"
            - "--revision=1"

          env:
            - name: TASK_DB_URL
              valueFrom:
                secretKeyRef:
                  name: daily-close-db
                  key: url
            - name: TASK_DB_USER
              valueFrom:
                secretKeyRef:
                  name: daily-close-db
                  key: username
            - name: TASK_DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: daily-close-db
                  key: password

          resources:
            requests:
              cpu: 250m
              memory: 384Mi
            limits:
              cpu: "1"
              memory: 768Mi

          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL

          volumeMounts:
            - name: tmp
              mountPath: /tmp

      volumes:
        - name: tmp
          emptyDir: {}
~~~

### Meaning of Key Fields

| Field | Meaning | What It Does Not Mean |
|---|---|---|
| `completions: 1` | One Pod must succeed for the Job to be complete | That the JVM ran only once across all faults |
| `parallelism: 1` | Target concurrent Pod count | Exactly-once execution |
| `restartPolicy: Never` | Failed Pod does not restart container in-place; Job spawns a new Pod | That Kubernetes won't retry |
| `backoffLimit: 2` | Retry/failure limit before the Job fails | That every error retries exactly twice |
| `activeDeadlineSeconds: 900` | Overall Job runtime cap | Per-SQL-statement timeout |
| `ttlSecondsAfterFinished: 86400` | Cleans up finished/failed Job after ~1 day | Deletes `TaskRepository` or business rows |
| `terminationGracePeriodSeconds: 30` | Gives the JVM a graceful shutdown window | Guarantees callbacks under `SIGKILL` |
| `requests/limits` | Pod CPU/RAM scheduling & caps | Full Java heap sizing |
| `automountServiceAccountToken: false` | Omits mounting K8s API token into Pod | Blocks general network access |
| `readOnlyRootFilesystem: true` | Prevents writes to image root filesystem | Eliminates need for `/tmp` |
| `emptyDir /tmp` | Gives runtime scratch space | Persistent storage after Pod exits |

Using `activeDeadlineSeconds` and `backoffLimit` together: **the active deadline can terminate the Job before all retries are exhausted**. OOMKills, image pull errors, node loss, and JDBC failures surface differently on Pods/Jobs; inspect Events and container statuses to classify them.

## 14. Applying the Job and Watching Progress

From the directory containing your manifest:

~~~bash
kubectl -n task-lab apply -f job.yaml

kubectl -n task-lab get job daily-close-20261123
kubectl -n task-lab describe job daily-close-20261123

kubectl -n task-lab get pods \
  -l batch.kubernetes.io/job-name=daily-close-20261123 \
  -o wide
~~~

The standard `batch.kubernetes.io/job-name` label is automatically attached to Job Pods on modern clusters; if no Pods appear, inspect `kubectl describe job` and actual labels.

Wait for Job completion:

~~~bash
kubectl -n task-lab wait \
  --for=condition=complete \
  job/daily-close-20261123 \
  --timeout=15m
~~~

**If the Job fails**, the `Complete` condition never becomes true and `wait` times out. Never assume "the app is still running" just because `wait` failed; inspect **conditions, Pod statuses, and Events**.

View logs for a single-Pod run:

~~~bash
kubectl -n task-lab logs \
  job/daily-close-20261123 \
  --all-containers=true \
  --timestamps=true
~~~

When retries spawn **multiple Pods**, `kubectl logs job/...` may show only one Pod's logs. List all Pods and inspect logs per Pod, especially failed ones.

~~~bash
kubectl -n task-lab get pods \
  -l batch.kubernetes.io/job-name=daily-close-20261123

kubectl -n task-lab logs pod/POD_NAME --timestamps=true
kubectl -n task-lab describe pod POD_NAME
~~~

`POD_NAME` is a placeholder to replace with an actual Pod name. With `restartPolicy: Never`, each Job retry creates a separate Pod; `kubectl logs --previous` only helps when **a container restarted within the same Pod**, not for fetching logs from an earlier retry Pod.

## 15. Distinguishing Job Complete, Pod Succeeded, and Container Exit Code

Kubernetes exposes multiple status layers:

| Observation | Meaning | What Else to Check |
|---|---|---|
| Job `Complete=True` | Job controller confirmed required completions | `TaskRepository` and business output |
| Job `Failed=True` | Job exceeded failure/deadline policy or hit a fatal condition | Pod/container termination reason, logs, data |
| Pod `Succeeded` | Relevant containers in the Pod exited cleanly | Business logic / `TaskExecution` |
| Pod `Failed` | A container failed or Pod terminated unsuccessfully | Exit code, `OOMKilled`, `DeadlineExceeded` |
| Container `exitCode=0` | JVM/container exited cleanly per exit policy | Does not prove complete business data |
| Container `exitCode≠0` | Container reported an error | Partial or full data may still have committed |
| `TaskExecution` `exitCode=0` | Spring Cloud Task recorded completion per policy | Does not replace unique keys/transactions |
| `TaskExecution` missing `endTime` | Framework has not written end timestamp | Process may still be alive or crashed abruptly |

Command to fetch Pod phases and names:

~~~bash
kubectl -n task-lab get pods \
  -l batch.kubernetes.io/job-name=daily-close-20261123 \
  -o wide
~~~

Extract termination info from Pod JSON (e.g., Linux/macOS shell):

~~~bash
kubectl -n task-lab get pod POD_NAME \
  -o jsonpath='{.status.containerStatuses[0].state.terminated.reason}{" "}{.status.containerStatuses[0].state.terminated.exitCode}{"\n"}'
~~~

If `state.terminated` is absent, the container may still be Running/Waiting. If the Pod has sidecars or multiple containers, select **the `daily-close` container specifically** instead of assuming index 0 is always the main task.

### Situations Where a Job Fails Without Creating Any TaskExecution

- Image pull failure (`ImagePullBackOff` or `ErrImagePull`).
- Pod unschedulable due to insufficient CPU/RAM/quota.
- Secret or key missing.
- JVM fails to start (bad JAR, incompatible Java version).
- Spring `ApplicationContext` fails before `TaskRepository` begins saving.
- Database/schema unavailable at startup.

In these cases, **having no `TaskExecution` does not mean Kubernetes never tried to launch**. Inspect `kubectl describe job/pod`, Events, and container logs/statuses.

## 16. Cross-Checking TaskRepository with SQL

After the Job finishes, connect to PostgreSQL using an account with **metadata read privileges** rather than using a migrator/superuser account for routine operational queries.

With the default Task schema and `TASK_` prefix:

~~~sql
SELECT
    TASK_EXECUTION_ID,
    TASK_NAME,
    START_TIME,
    END_TIME,
    EXIT_CODE,
    EXIT_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'daily-close-task'
ORDER BY TASK_EXECUTION_ID DESC
LIMIT 20;
~~~

Inspect parameters of a single run (never print sensitive data):

~~~sql
SELECT
    TASK_EXECUTION_ID,
    TASK_PARAM
FROM TASK_EXECUTION_PARAMS
WHERE TASK_EXECUTION_ID = :task_execution_id;
~~~

**DDL note:** column names in `TASK_EXECUTION_PARAMS` and auxiliary tables can vary across versions/dialects, so check your actual schema before running SQL. The snippet uses `TASK_PARAM` as a common reference column; adjust to match your migrated DDL if different.

Keep in mind:

- `TaskExecutionId` differs from `Job name` and business keys.
- A Job retry spawning a new Pod creates a **new `TaskExecution`**.
- When a process dies abnormally, the `TaskExecution` row may lack `END_TIME`.
- `ERROR_MESSAGE`/arguments may contain sensitive data; grant read access minimally.
- If runtime uses a custom schema/prefix, qualify the table name accordingly, e.g., `task_meta.TASK_EXECUTION`.

### If the Application Uses Spring Batch

When a task runs a Batch Job, **`JobRepository`** holds `JobInstance`, `JobExecution`, `StepExecution`, and checkpoints separately. Never read `TaskRepository` alone and conclude a Batch Job definitely `COMPLETED`. Inspect `BATCH_*` metadata and business output, especially with multiple Jobs or remote partitioning.

## 17. Cross-Checking the Business Result Table

Query the daily-close record:

~~~sql
SELECT
    tenant_id,
    business_date,
    revision,
    total_amount,
    created_at
FROM finance.daily_close_result
WHERE tenant_id = 'tenant-A'
  AND business_date = DATE '2026-11-23'
  AND revision = 1;
~~~

Expected after the first run:

~~~text
tenant_id   | business_date | revision | total_amount
------------+---------------+----------+-------------
tenant-A    | 2026-11-23    | 1        | 123.45
~~~

Because of `PRIMARY KEY(tenant_id, business_date, revision)`, two rows cannot share **the same business key**. If a Job retries with identical inputs, the service logs `ALREADY_APPLIED` and returns success in this demo rather than inserting a duplicate.

To check for duplicate rows per key (diagnostic check; the PRIMARY KEY already blocks duplicates):

~~~sql
SELECT tenant_id, business_date, revision, COUNT(*) AS rows_for_key
FROM finance.daily_close_result
GROUP BY tenant_id, business_date, revision
HAVING COUNT(*) > 1;
~~~

Expect **0 rows**. This result **does not prove** real-world workflows outside the lab are completely exactly-once if external API/message side effects exist. In production, enforce idempotency across external systems as well.

## 18. Rehearsing Post-Commit Failure and Automatic Retry

This is the most important part for understanding the difference between a **Kubernetes Job failure** and a **business outcome**.

### Step A — Create an Intentionally Failing Job

Copy `job.yaml` **in your learning project** and change:

- `metadata.name: daily-close-failure-20261122`.
- `spec.backoffLimit: 1`, for easy observation.
- Arguments `--date=2026-11-22` plus `--fail-after-commit`.
- Keep tenant/revision and database configuration identical.

Do not edit `spec.template` on an existing Job with `kubectl apply` expecting Kubernetes to update it: **a Job's Pod template is generally immutable**. Create a **new Job name** for this rehearsal.

~~~yaml
# Only the args section that changes in the new Job manifest:
args:
  - "--tenant=tenant-A"
  - "--date=2026-11-22"
  - "--revision=1"
  - "--fail-after-commit"
~~~

Then run:

~~~bash
kubectl -n task-lab apply -f job-failure.yaml
kubectl -n task-lab get job daily-close-failure-20261122
kubectl -n task-lab get pods \
  -l batch.kubernetes.io/job-name=daily-close-failure-20261122
~~~

### Step B — Observe the Outcome

Each time a JVM reaches `DailyCloseService`, it:

1. Inserts the business-key record and commits.
2. Throws `IllegalStateException` after commit.
3. Exits with failure, letting the Kubernetes Job controller retry per `backoffLimit`.

After retries finish, inspect each Pod's logs. You should see:

~~~text
First run:  result=APPLIED
Next run:   result=ALREADY_APPLIED
Both runs:  Simulated failure after business commit
~~~

Even though the Job ends **Failed**, `finance.daily_close_result` holds **one** row for `tenant-A, 2026-11-22, revision=1`.

**Do not assume an exact Pod count** solely from `backoffLimit`: the controller applies failure-counting, backoff, and replacement rules; inspect actual `status.failed` and the Pod list. An image pull or pre-commit DB error leaves a different footprint.

### Step C — Re-run After Fixing the Error

Create **a new Job with a different name**, identical `tenant/date/revision`, and **omit `--fail-after-commit`**. It detects the existing record, logs `ALREADY_APPLIED`, and completes successfully per the demo design.

This illustrates **idempotent retry**, not "every retry must reprocess from scratch". In production, also verify input fingerprints/snapshots and external side effects.

## 19. Creating a Daily Automated CronJob

Kubernetes CronJobs spawn Jobs on a schedule. To practice without waiting until the next day, create the CronJob first and then spawn a manual Job from its template.

Example `cronjob.yaml`:

~~~yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: daily-close-nightly
  namespace: task-lab
  labels:
    app: daily-close-task

spec:
  schedule: "0 2 * * *"
  timeZone: "Asia/Ho_Chi_Minh"
  concurrencyPolicy: Forbid
  startingDeadlineSeconds: 600
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 2

  jobTemplate:
    spec:
      backoffLimit: 2
      activeDeadlineSeconds: 900
      ttlSecondsAfterFinished: 86400

      template:
        spec:
          restartPolicy: Never
          terminationGracePeriodSeconds: 30
          automountServiceAccountToken: false

          securityContext:
            runAsNonRoot: true
            runAsUser: 10001

          containers:
            - name: daily-close
              image: registry.example.org/training/daily-close-task:1.0.0
              imagePullPolicy: IfNotPresent
              args:
                - "--tenant=tenant-A"
                - "--previous-day"
                - "--revision=1"

              env:
                - name: TASK_DB_URL
                  valueFrom:
                    secretKeyRef:
                      name: daily-close-db
                      key: url
                - name: TASK_DB_USER
                  valueFrom:
                    secretKeyRef:
                      name: daily-close-db
                      key: username
                - name: TASK_DB_PASSWORD
                  valueFrom:
                    secretKeyRef:
                      name: daily-close-db
                      key: password

              resources:
                requests:
                  cpu: 250m
                  memory: 384Mi
                limits:
                  cpu: "1"
                  memory: 768Mi
~~~

The CronJob manifest is shorter than section 13's Job to highlight schedule fields. In production, apply the exact same `securityContext`, read-only root filesystem, `/tmp`, and network/Secret restrictions. Never treat a shorter sample as permission to relax security controls.

### Meaning of CronJob Fields

| Field | Meaning | Limit |
|---|---|---|
| `schedule: "0 2 * * *"` | Spawns a Job daily at 02:00 | Does not set Java's business date |
| `timeZone: "Asia/Ho_Chi_Minh"` | Interprets cron schedule in this timezone | Does not configure the JVM's `ZoneId` |
| `concurrencyPolicy: Forbid` | Skips next tick if **previous Job of this same CronJob** is still running | Does not block manual Jobs or other CronJobs |
| `startingDeadlineSeconds: 600` | Skips runs delayed by more than ~10 minutes | Can drop a scheduled run; must be monitored |
| `successfulJobsHistoryLimit: 3` | Retains up to a few succeeded Jobs | Does not replace log retention |
| `failedJobsHistoryLimit: 2` | Retains a few failed Jobs | Does not guarantee Pod logs remain readable forever |
| `jobTemplate` | Template for Jobs created by CronJob | Each spawned Job still has its own lifecycle/retries |

`Forbid` is not a distributed business lock: if two distinct CronJobs or an operator launch a Job manually for the same period, Pods can still run concurrently. Under rare controller edge cases, a CronJob may even spawn two Jobs for one schedule tick or miss a tick; therefore **idempotency** remains essential.

### Business Date Calculation Pitfall

The example uses `--previous-day` with `Asia/Ho_Chi_Minh` inside Java to compute yesterday at launch time. When a Job reliably runs at 02:00, that works for a demo. However, if **a schedule runs late across midnight**, `previous-day` yields a business date that does not match the original tick.

In production, establish **a deterministic way to bind business dates per scheduled run**: have the scheduler pass a precomputed `--date=yyyy-MM-dd`, or pass the orchestrator's scheduled timestamp with well-tested rules. Never use Pod start time as the business key when backfilling older periods.

## 20. Applying, Inspecting Schedules, and Triggering the CronJob Immediately

Create the CronJob:

~~~bash
kubectl -n task-lab apply -f cronjob.yaml

kubectl -n task-lab get cronjobs
kubectl -n task-lab describe cronjob daily-close-nightly
~~~

Spawn a Job immediately from its template **without waiting for 02:00**:

~~~bash
kubectl -n task-lab create job daily-close-ad-hoc-001 \
  --from=cronjob/daily-close-nightly

kubectl -n task-lab get job daily-close-ad-hoc-001
kubectl -n task-lab logs job/daily-close-ad-hoc-001
~~~

`kubectl create job --from=cronjob/...` copies `jobTemplate` at invocation time. It **does not recompute arguments from a cron tick**, so in the demo `--previous-day` resolves relative to the ad-hoc run time.

To pause scheduling temporarily, set `spec.suspend: true` in the manifest and apply. Suspending **does not stop already-running Jobs**. When unsuspending, review `startingDeadlineSeconds` and missed-schedule behavior to avoid unexpected catch-up runs.

### Listing Jobs Created by a CronJob

~~~bash
kubectl -n task-lab get cronjob daily-close-nightly
kubectl -n task-lab get jobs -l app=daily-close-task
kubectl -n task-lab get pods -l app=daily-close-task
~~~

Kubernetes attaches `ownerReferences`/labels to spawned Jobs; to distinguish Jobs from different CronJobs, assign distinct labels in `jobTemplate.metadata.labels` or inspect `ownerReferences`. Never infer Job ownership from name prefixes alone if multiple schedules share a prefix.

## 21. Unified Observation Workflow: Logs, Events, and SQL

A reliable execution check follows four investigation steps:

~~~mermaid
flowchart TD
    A["Job created"] --> B{"Did Pod run?"}
    B -- "No" --> C["Events: scheduling, image, Secret, quota"]
    B -- "Yes" --> D["Logs and container exit code"]
    D --> E{"Does TaskExecution exist?"}
    E -- "No" --> F["Bootstrap, DataSource, schema, JVM"]
    E -- "Yes" --> G["End time, exit code, error message"]
    G --> H["Check business output by business key"]
    H --> I{"Result correct and duplicate-free?"}
    I -- "Yes" --> J["Mark completed per policy"]
    I -- "No" --> K["Investigate transaction/idempotency/retry"]
~~~

### Recommended Operational Sequence

1. `kubectl get cronjobs/jobs/pods`: identify the Job and all Pod retry attempts.
2. `kubectl describe job/pod`: inspect Events, deadlines, OOMKills, image pulls, Secrets, quotas.
3. `kubectl logs` per Pod: check date/tenant/revision and `APPLIED` vs. `ALREADY_APPLIED`.
4. Query `TaskRepository`: correlate `TaskExecution` ID, start/end times, and exit code.
5. Query the business table: verify a single row matching the exact business key.
6. If using Spring Batch, query `JobRepository` and `StepExecution`/checkpoints.
7. Trigger manual retries only after confirming whether another worker/Job is still running and how far business state committed.

**A Pod `Failed` status does not prove the business transaction rolled back.** In particular, network errors after the server receives a request or a JVM crash post-commit can look like failure to callers while data has already changed.

## 22. Observability Without HTTP Health Endpoints

`WebApplicationType.NONE` applications do not need `/actuator/health` to run as finite tasks. For Kubernetes Jobs, observe:

| Observability Source | Collection Mechanism |
|---|---|
| Job/Pod status | Kubernetes API, Job controller metrics, Events |
| Exit code | Container `terminated.exitCode` |
| Task lifecycle | `TaskRepository`, `TaskExplorer` |
| Logs | Centralized log collector and `kubectl logs` while Pods remain |
| Duration/failure metrics | Micrometer/OTLP pushed or flushed before JVM exit |
| Business output | Query by tenant/date/revision key |
| Traces | OpenTelemetry/Micrometer correlated via `TaskExecution` ID when available |

Because Jobs can be very short-lived, **pull-based metrics scrapers** may miss them. When using async exporters, ensure telemetry flushes/closes cleanly during controlled shutdown, accepting that `SIGKILL` bypasses callbacks.

Useful alerting signals:

- A new Job reached `Failed` or hit `activeDeadlineSeconds`.
- No Job succeeded for a mandatory business date before SLA deadline.
- Unusually high Job/Pod retry counts.
- A `TaskExecution` stayed open too long or exited nonzero.
- Business result missing for a tenant/date or reported a conflict.
- PostgreSQL connection pool/quota saturation.

Never put high-cardinality tenant IDs, transaction IDs, or `TaskExecution` IDs into **low-cardinality metric labels** at scale; use controlled structured logs/trace attributes instead.

## 23. Resources, Security, and Cleanup

### Security

- Use scanned images pinned by immutable tag or digest.
- Run containers non-root, forbid privilege escalation, and restrict filesystem writes.
- Do not mount Kubernetes API tokens unless the worker calls the API.
- Inject Secrets via `secretKeyRef`/secret managers; never pass passwords via CLI args.
- Grant the runtime DB role only DML on `TaskRepository` and required business tables.
- Restrict outbound traffic with NetworkPolicies to only needed PostgreSQL/APIs.
- Never log raw `TaskExecution` arguments if they contain sensitive data.
- Separate **`kubectl` operator permissions** from **in-Pod ServiceAccount permissions**.

### Resources

- Size `requests` so Pods schedule reliably, and `limits` to cover JVM heap + native memory.
- Concurrent retry Pods or parallelism multiply DB connection pool totals.
- Set `activeDeadlineSeconds` comfortably above normal runtime + startup overhead, while remaining bounded.
- Balance `terminationGracePeriodSeconds` against acceptable commit/cleanup time.
- `parallelism: 1` does not replace business locks or unique constraints.

### Retention

`ttlSecondsAfterFinished` automatically deletes Jobs/Pods after finishing. Once deleted, `kubectl logs` loses the Pods' logs. Ship logs and store `TaskRepository` outside Job/Pod lifetimes with proper retention and backups.

Never bulk-delete `TASK_EXECUTION` or `TASK_EXECUTION_PARAMS` simply because Kubernetes garbage-collected the Jobs. Those tables serve auditing and downstream operational processes. If metadata pruning is required, run a controlled maintenance workflow.

## 24. Common Troubleshooting Reference

| Symptom | Possible Cause | Diagnosis |
|---|---|---|
| Job stays `Pending` | Quota exhausted, insufficient CPU/RAM, node selector or taint | `kubectl describe pod` and Events |
| `ImagePullBackOff` | Wrong image/registry/credentials | Pod Events, `imagePullSecrets`, image digest |
| `CreateContainerConfigError` | Missing Secret or key | Pod describe and Secret metadata |
| JVM throws `UnsupportedClassVersionError` | JRE in container image incompatible with JAR | Build vs. runtime Java version |
| Task cannot reach DB | DNS, NetworkPolicy, URL, Secret, or TLS | Connectivity and JDBC error details |
| `relation TASK_EXECUTION does not exist` | Metadata schema not migrated or wrong prefix | `TaskRepository` DDL and datasource |
| `permission denied for sequence` | Runtime role lacks privileges to allocate `TaskExecution` IDs | DDL, sequence/table type, and grants |
| Job `Completed` yet no output | Runner returned before async work or logic bug | Logs, `TaskExecution`, business SQL |
| Pod `Failed` yet output exists | Crash after commit, external side effects already ran | Business key/idempotency and `TaskRepository` |
| Multiple Pods for one Job | Retries or duplicate starts during failure windows | Pod list, `backoffLimit`, and Job conditions |
| CronJob spawns no Jobs | Suspended, schedule not yet due, missed deadline, controller error | Describe CronJob, `schedule`/`timeZone` |
| CronJob runs late on wrong date | `LocalDate.now()` evaluated at Pod start time | Pass deterministic business-date source |
| CronJob spawns overlapping runs | `Allow`, multiple CronJobs, manual Job, or controller edge case | Job owners/labels and business keys |
| `kubectl wait` times out | Job `Failed` or not yet `Complete` | Get/describe Job, conditions, Pod statuses |
| Logs vanish after a few days | TTL/history cleanup | Centralized logging and retention |
| Exit code 0 when business failed | Swallowed exception or unawaited future | `ApplicationRunner`, exit-code mapping |
| Pod `OOMKilled` | Heap/native memory exceeded limits | Resources, GC logs, container termination |
| Cannot edit args of old Job | Pod template is immutable | Create a newly named Job with updated args |
| Batch Job `FAILED` while task succeeded | Batch status not wired to task exit policy | `fail-on-job-failure` or custom runner |

## 25. Practice Acceptance Checklist

- [ ] Compatible Spring Boot/Spring Cloud BOM selected and JAR builds cleanly on learner's machine.
- [ ] Application sets `web-application-type: none`, runner executes work and exits JVM.
- [ ] PostgreSQL has **version-matched Spring Cloud Task DDL** and a business result table with a unique key.
- [ ] Secret created in namespace; no real credentials appear in manifests or logs.
- [ ] Container image pushed and pullable by cluster.
- [ ] Job `daily-close-20261123` spawns a Pod, logs `APPLIED`, and completes.
- [ ] `TaskRepository` contains a `TaskExecution` with matching start/end/exit code.
- [ ] `daily_close_result` has only one row per `tenant/date/revision`.
- [ ] CronJob sets appropriate `schedule`, `timeZone`, `concurrencyPolicy`, and `startingDeadlineSeconds`.
- [ ] Can trigger an immediate Job from CronJob via `kubectl create job --from=cronjob`.
- [ ] `--fail-after-commit` rehearsal: Job fails while retries never duplicate rows.
- [ ] Manual retry after removing failure flag returns `ALREADY_APPLIED`.
- [ ] Can inspect Pod Events, exit codes, and logs for **every Pod** of a Job.
- [ ] Can distinguish Job/Pod state from `TaskExecution` state and business state.
- [ ] Backup/retention plan defined for `TaskRepository` and centralized logs.
- [ ] Verified timezone, business-date computation, and catch-up policy for missed schedules.
- [ ] Does not treat `backoffLimit`, `Forbid`, or `parallelism: 1` as an exactly-once guarantee.

## 26. Conclusion

A **Kubernetes Job** fits running a finite Spring Cloud Task on demand; a **CronJob** fits spawning Jobs on a schedule. The crux is not merely getting a Pod to run: every launch must be observed across **Job/Pod**, **`TaskExecution`**, and **business results**. Those layers can diverge whenever timeouts, crashes, or retries happen.

With a synchronous `ApplicationRunner`, a persistent PostgreSQL `TaskRepository`, a unique business key, and Kubernetes manifests enforcing proper deadlines/retries/resources/security, you can build scheduled or on-demand tasks that are **observable, operable, and safely retryable**. Moving from lab to production, add formal migrations, least-privilege roles, deterministic business-date inputs, telemetry, and crash-window recovery runbooks.

### References

- [Spring Cloud Task — Reference](https://docs.spring.io/spring-cloud-task/reference/)
- [Spring Cloud Task — Features, DataSource, and Schema Initialization](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Cloud — Release Train Compatibility](https://spring.io/projects/spring-cloud/)
- [Kubernetes — Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/)
- [Kubernetes — CronJobs](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)
- [Kubernetes — Job API Reference](https://kubernetes.io/docs/reference/kubernetes-api/batch/job-v1/)
- [Kubernetes — CronJob API Reference](https://kubernetes.io/docs/reference/kubernetes-api/batch/cron-job-v1/)
- [kubectl wait](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_wait/)
