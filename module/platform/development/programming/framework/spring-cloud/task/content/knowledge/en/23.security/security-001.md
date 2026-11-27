# Protecting Secrets from Persisted Arguments and Logs

In **Spring Cloud Task**, a Spring Boot application starts, receives arguments, performs a finite amount of work, updates the status of `TaskExecution` in **TaskRepository**, and then terminates. This metadata persistence mechanism aids traceability and operations for data import, reporting, maintenance, or scheduled tasks. However, it also creates an important security surface: **command-line arguments can be persisted long-term in the database**. If passwords, API tokens, or signing keys are passed through arguments, secrets may remain in the TaskRepository even after the process has exited.

This lesson belongs to the **Security** chapter and focuses on how to prevent leaking **secrets** in **Task arguments**, **Spring Batch JobParameters**, **`exitMessage`**, **`errorMessage`**, exceptions, and application logs. We will use a partner invoice import task as an example, designing credential provisioning via environment/Secret store, safe logging, access control on metadata, and tests that prove no secrets are leaked.

> **Core Principle:** Secrets are needed for **execution**, but usually **do not need to exist in arguments used for traceability**. Pass *business identifiers and non-sensitive references* through arguments; provide *credential values* through a secure channel and do not write them into metadata, logs, metrics, traces, or exception messages.

## 1. Where Can Secrets Leak?

A task may be triggered from a CronJob, Spring Cloud Data Flow, an API launcher, or a terminal. Imagine the following command:

~~~bash
# DO NOT USE: this is an intentionally flawed example.
java -jar partner-import-task.jar \
  --business-date=2026-11-23 \
  --partner-id=partner-a \
  --api-token=DEMO_DO_NOT_USE_AS_A_REAL_SECRET
~~~

The value after `--api-token=` can appear in multiple places:

| Location | Why is it risky? | Who can see it? |
| --- | --- | --- |
| **`TASK_EXECUTION_PARAMS`** | Spring Cloud Task writes launch arguments to TaskRepository | People/accounts reading metadata, admin tools, backups |
| **Process command line** | The OS/container runtime retains argv while the process is alive | People with permission to inspect processes/hosts/containers |
| **Kubernetes Pod spec** | `args` resides in the Pod template or Job manifest | People with permission to read Pods/Jobs, API audit logs |
| **Shell history, CI/CD logs** | Launch commands are recorded/saved by the terminal or pipeline | People with permission to view history or logs |
| **Spring Batch `JobParameters`** | If `api-token` is copied into JobParameters, Batch stores it in its own repository | People with permission to read `BATCH_JOB_EXECUTION_PARAMS` |
| **Application logs** | `log.info("args={}", args)` or unfiltered request/response logging | Readers of the centralized logging system |
| **`EXIT_MESSAGE` / `ERROR_MESSAGE`** | Listeners or exceptions contain raw tokens | Viewers of TaskExecution and error detail pages |
| **Metrics, traces, events** | Tokens accidentally become tag/span attributes/event payloads | Users querying monitoring systems/message brokers |

**Not storing passwords in arguments** is the first measure, but not the entire solution. A secret supplied via environment variables or files can still leak if the code prints `Environment`, dumps configuration, logs the `Authorization` header, or puts raw exceptions into `exitMessage`.

### Data Flow Diagram

~~~mermaid
flowchart TD
    L["Cron / API / CLI launcher"] --> A["Command-line arguments"]
    L --> S["Secret manager / Kubernetes Secret"]
    A --> P["Spring Cloud Task process"]
    A --> H[("TASK_EXECUTION_PARAMS<br/>persisted metadata")]
    S --> E["Env / mounted secret file"]
    E --> P
    P --> B["Business logic / HTTP / JDBC"]
    P --> X[("TASK_EXECUTION<br/>EXIT_MESSAGE, ERROR_MESSAGE")]
    P --> G[("Logs / traces / metrics")]
    B --> G
    B --> R[("Business outcome")]
    H -. "read access, backup" .-> U["Operators / tools"]
    X -. "read access" .-> U
    G -. "read access" .-> U
~~~

The goal is not to “hide a token by renaming it,” but to **restrict the token from entering streams designed to store, search, and share metadata**.

## 2. What Does Spring Cloud Task Actually Store?

A single run is represented by `TaskExecution`. According to the official documentation, this information includes `executionId`, `taskName`, `startTime`, `endTime`, `exitCode`, `exitMessage`, `errorMessage`, and the list of **arguments**. In the default schema:

| Table / Column | Data | Risk if a secret is included |
| --- | --- | --- |
| `TASK_EXECUTION` | Metadata for a run, `EXIT_MESSAGE`, `ERROR_MESSAGE` | Custom messages or stack traces can expose secrets |
| `TASK_EXECUTION_PARAMS` | `TASK_EXECUTION_ID`, `TASK_PARAM` | Argument strings are retained after the Task finishes |
| `TASK_TASK_BATCH` | Links TaskExecution and JobExecution (if Batch is integrated) | Can lead readers to Batch metadata |
| `BATCH_JOB_EXECUTION_PARAMS` | `PARAMETER_NAME`, `PARAMETER_VALUE`, and the identifying flag in Spring Batch 5.x | Secrets passed in JobParameters persist durably |
| Business tables | Source/target data and processing status | Can be exposed via error codes or raw payload logs |

According to the Spring Cloud Task reference schema, `TASK_EXECUTION_PARAMS.TASK_PARAM` has a `VARCHAR(2500)` limit; `TASK_EXECUTION.EXIT_MESSAGE` and `ERROR_MESSAGE` are also documented as `VARCHAR(2500)`. Actual limits and DDL depend on the version/database; **a character-limited column does not mean the value is encrypted or masked**.

**A common mistake:**

~~~text
--spring.datasource.password=real-password
--partner-api-key=real-api-key
--storage.s3.secret-key=real-secret-key
~~~

Spring Boot can use those values as **application configuration**; at the same time, they remain **input arguments** and can end up in Task metadata. Naming a property `password` or `secret` does not mean Spring Cloud Task automatically ignores or redacts the value when writing `TASK_EXECUTION_PARAMS`.

### 2.1. `TASK_EXECUTION_PARAMS` Differs from JobParameters

Spring Cloud Task and Spring Batch have separate repositories by role:

~~~text
Spring Cloud Task
  TaskExecution #4101
    arguments = [
      "--business-date=2026-11-23",
      "--partner-id=partner-a"
    ]

Spring Batch (if the application has a Batch Job)
  JobExecution #9001
    JobParameters = {
      businessDate: "2026-11-23",
      sourceId: "partner-a"
    }
~~~

**Do not copy secrets from Task arguments to Batch JobParameters.** In Spring Batch, `BATCH_JOB_EXECUTION_PARAMS` stores the parameters passed to the Job, including **non-identifying** parameters. The `identifying=false` flag only changes whether the parameter contributes to identifying the `JobInstance`; **it does not mean “do not persist” or “non-sensitive”**.

If a Task is launched through Spring Cloud Data Flow, the UI and launch/execution history may also display arguments depending on access permissions. Therefore, treat every orchestration system as a surface that can record and display metadata, not as a default secret-keeping channel.

## 3. Classify Data Before Designing Parameters

A straightforward approach is to establish an **allowlist** for fields permitted to appear in metadata:

| Value | Include in Task argument? | Reason |
| --- | --- | --- |
| `--business-date=2026-11-23` | **Yes** | Business date usable for reconciliation |
| `--operation=import` | **Yes** | Processing mode, not a secret |
| `--report-version=2` | **Yes** | Output version identifier |
| `--source-id=partner-a-feed-42` | Yes **if classified as non-sensitive** | IDs can become sensitive data in some systems |
| `--credential-ref=partner-a-service` | Yes **if the reference is non-sensitive** | Merely a logical key for a resolver to fetch the real secret |
| `--access-token=...` | **No** | Credential granting direct access |
| `--db-password=...` | **No** | Database password |
| `--private-key=...` | **No** | Signing key or decryption key |
| `--connection-string=...password=...` | **No** | Connection string containing credentials |
| `--customer-email=...` | Restricted / check PII policy | Not a token, but may be personal data |

**Classify by value and purpose, not solely by key name.** A `source-id` containing an email or a path to confidential data should also not be written verbatim to logs. A `credential-ref`, if it is a URL with a pre-signed token or an access code that can be used directly, must also be treated as a secret.

### 3.1. Design Two Separate Input Channels

~~~text
Channel A — persistable arguments:
  --business-date=2026-11-23
  --partner-id=partner-a
  --run-mode=scheduled

Channel B — runtime-only secrets:
  PARTNER_API_TOKEN (Secret / vault)
  TASK_DB_PASSWORD (Secret / vault)
  TLS_PRIVATE_KEY (secret volume or secret manager)
~~~

**No channel is 100% secure.** Channel B reduces the risk of writing to TaskRepository and argv, yet the process can still access the secret; access controls, node/container security, logs, dumps, and rotation are still required.

## 4. Incorrect and Correct Examples When Launching the Application

### 4.1. Incorrect: Putting Credentials on the Command Line

~~~bash
# Counter-example only; do not use with real credentials.
java -jar partner-import-task.jar \
  --business-date=2026-11-23 \
  --partner-api-token=DEMO_SECRET_DO_NOT_USE
~~~

Risks:

- The token can be stored in `TASK_EXECUTION_PARAMS`.
- Shell history and process argv can retain the exact command.
- Kubernetes Job/Pod specs and orchestration platforms can record `args`.
- If the code has `log.info("Args: {}", args.getSourceArgs())`, the token also appears in logs.

**Renaming to an obscure property** like `--p-a-t=...` does not solve the problem; the string is still present in arguments.

### 4.2. Better Approach: Credentials in Environment / Secret Provider

~~~bash
# DEMO_ONLY: pass only non-sensitive parameters.
java -jar partner-import-task.jar \
  --business-date=2026-11-23 \
  --partner-id=partner-a
~~~

In a Kubernetes environment, `PARTNER_API_TOKEN` is provided via a Secret rather than an argument. Example Spring Boot configuration:

~~~yaml
spring:
  application:
    name: partner-import-task
  main:
    web-application-type: none
  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}
  cloud:
    task:
      initialize-enabled: false

partner:
  api:
    token: ${PARTNER_API_TOKEN}
~~~

In this example, the environment variables must exist when the process starts; token values **must not be hardcoded in `application.yml`**. Do not commit `.env` files containing secrets or bake those files into the image.

**Limitation:** interpolating `${PARTNER_API_TOKEN}` only puts the credential into the Spring Environment; if the application prints all properties, exposes Actuator too broadly, or generates exceptions containing the token, the secret can still leak. A good secret delivery channel must be paired with **no-logging discipline**.

## 5. Kubernetes Secret: Env and Mounted Volume

A Kubernetes Job can receive secrets via `env[].valueFrom.secretKeyRef`:

~~~yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: partner-import-demo
  namespace: batch-jobs
spec:
  backoffLimit: 1
  template:
    spec:
      serviceAccountName: partner-import-task
      automountServiceAccountToken: false
      restartPolicy: Never
      containers:
        - name: task
          image: registry.example.com/batch/partner-import-task:1.0.0
          args:
            - "--business-date=2026-11-23"
            - "--partner-id=partner-a"
          env:
            - name: TASK_DB_URL
              valueFrom:
                secretKeyRef:
                  name: task-db-credentials
                  key: jdbc-url
            - name: TASK_DB_USER
              valueFrom:
                secretKeyRef:
                  name: task-db-credentials
                  key: username
            - name: TASK_DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: task-db-credentials
                  key: password
            - name: PARTNER_API_TOKEN
              valueFrom:
                secretKeyRef:
                  name: partner-api-credentials
                  key: token
~~~

Secret names, images, namespaces, and ServiceAccounts are illustrative only. A real environment must create these resources and configure appropriate network policies/permissions. `automountServiceAccountToken: false` makes sense when the Task **does not need to call the Kubernetes API**; if the application genuinely needs the API, grant a minimal ServiceAccount and configure tokens as needed.

**Secrets should not be written in manifests in plaintext**. Kubernetes Secret base64 **is not encryption**: anyone who can read the base64 value can decode it. Restrict `get/list/watch` permissions on Secrets with RBAC, enable **encryption at rest** for etcd when using Kubernetes, and manage access to backup systems.

### 5.1. Passwords via Env Are Not Completely Safe

Environment variables avoid persisting secrets in Task arguments, but they can still be read by:

- Code running **inside the same container/process**.
- Users with `exec`/debug permissions or access to the host/node depending on configuration.
- Crash dumps, diagnostic collectors, or libraries that print all of `System.getenv()`.
- Privileged components in the infrastructure.

If higher security is required, consider a secret manager or **mounted file/Secret Store CSI Driver**; mount only into containers that need it, restrict filesystem permissions, and never dump file contents to logs.

### 5.2. Mounted Secret Instead of Env

Example mounting a token into a dedicated path:

~~~yaml
volumes:
  - name: partner-token
    secret:
      secretName: partner-api-credentials
      items:
        - key: token
          path: token
containers:
  - name: task
    image: registry.example.com/batch/partner-import-task:1.0.0
    volumeMounts:
      - name: partner-token
        mountPath: /var/run/secrets/partner
        readOnly: true
~~~

This is an **illustrative Pod spec snippet** that must be placed under `spec.template.spec` and combined with the complete Job definition. The application reads the token from `/var/run/secrets/partner/token` through a dedicated service, uses it in the HTTP client, and **does not print sensitive file paths or token contents in logs**.

Mounted files help separate secrets from argv/env if the code actually reads the file directly. However, file contents can still be read by legitimate processes; Pod/container permissions, node security, secret issuance policies, and rotation are still needed. When using Kubernetes Secrets as env vars, changing a Secret **generally does not automatically update the env value in a running Pod**; with mounted volumes, updates occur conditionally and with latency, with exceptions like `subPath`. For **short-lived Tasks**, a practical strategy is typically **fetching a fresh secret on startup for each run**, accompanied by a revocation workflow for old tokens.

## 6. Java Code: Reading Arguments Safely Without Logging Secrets

The import task should receive **business-date** and **partner-id** via `ApplicationArguments`, while the token is supplied by a configuration provider and passed only to the HTTP client.

~~~java
import java.time.LocalDate;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ImportTaskConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(ImportTaskConfiguration.class);

    @Bean
    ApplicationRunner runImport(
            PartnerImportService service,
            @Value("${partner.api.token}") String apiToken) {

        return args -> {
            LocalDate businessDate = LocalDate.parse(
                    required(args, "business-date"));
            String partnerId = required(args, "partner-id");

            // Allowlist logging: do not print all args or Environment.
            log.info(
                    "Import starting: operation=partner-import, date={}",
                    businessDate);

            // The service code is responsible for not logging apiToken.
            ImportResult result =
                    service.importOrders(partnerId, businessDate, apiToken);

            log.info("Import completed: accepted={}, rejected={}",
                    result.accepted(), result.rejected());
        };
    }

    private static String required(
            ApplicationArguments args, String key) {
        List<String> values = args.getOptionValues(key);
        if (values == null || values.size() != 1 ||
                values.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "Missing or invalid option: " + key);
        }
        return values.get(0);
    }
}

interface PartnerImportService {
    ImportResult importOrders(
            String partnerId, LocalDate date, String apiToken);
}

record ImportResult(long accepted, long rejected) {}
~~~

This snippet is a **component example**: you must provide a `PartnerImportService` bean, the Spring Cloud Task dependency, a DataSource, and application configuration. `ImportResult` records processed counts and contains no tokens.

**Note on data lifecycle in the JVM:** `String apiToken` remains in memory and may appear in heap dumps. For secrets needing stronger protection, prefer client/credential providers that manage secrets internally, avoid duplicating the `String` in many places, and control dump policies. Using `char[]` does not make a system automatically safe if the HTTP/JDBC library ultimately converts it back into a `String`.

### 6.1. Logging Practices to Avoid

~~~java
// DO NOT do this in production.
log.info("Arguments: {}", args.getSourceArgs());
log.debug("All environment variables: {}", System.getenv());
log.info("Partner configuration: {}", partnerProperties);
log.error("HTTP request: {}", request);
log.error("HTTP response: {}", response);
~~~

Depending on the library, an object's `toString()` may contain `Authorization`, cookies, URLs with tokens, credentials, or sensitive payload contents. Even at the `DEBUG` level there is risk: log levels may be temporarily enabled and forgotten, and logs get shipped to backends with long retention.

Replace with **allowed fields**:

~~~java
log.info(
    "Partner import started: date={}, operation={}",
    businessDate, "import-orders");

log.warn(
    "Partner API rejected request: reasonCode={}, retryable={}",
    "AUTH_REJECTED", false);
~~~

Do not log raw `partnerId` if that ID is classified as sensitive; you can use a stable internal code, a keyed hash, or a controlled incident reference.

## 7. Exceptions and ERROR_MESSAGE: Easily Overlooked Leak Points

Spring Cloud Task stores **`ERROR_MESSAGE`** when terminating due to an exception; the documentation notes it can contain the **stack trace**. A stack trace typically includes the **exception message**, and messages are sometimes generated by third-party libraries and can contain:

- URLs with query `?api_key=...`.
- JDBC URLs containing passwords.
- Response bodies from partner APIs (which may contain tokens or PII).
- File paths, internal records, or authentication headers.
- Invalid arguments containing raw user values.

Dangerous example:

~~~java
throw new IllegalArgumentException(
        "Invalid token: " + apiToken);
~~~

Even without a single `log.error(...)` line, this exception can still be written into **`TASK_EXECUTION.ERROR_MESSAGE`**. Similarly, a listener calling `taskExecution.setExitMessage(exception.getMessage())` can additionally persist credentials in `EXIT_MESSAGE`.

### 7.1. Use Non-Sensitive Reason Codes

~~~java
try {
    partnerClient.executeImport();
} catch (PartnerAuthenticationException ex) {
    // Do not include ex.getMessage() or raw response in logs.
    log.warn("Partner import failed: reasonCode=AUTH_REJECTED");

    // Fixed message containing no tokens or partner data.
    throw new IllegalStateException("PARTNER_AUTH_REJECTED");
}
~~~

The purpose of this example is to **block the path from a raw exception to ERROR_MESSAGE**. By intentionally not attaching `ex` as the cause of the rethrown exception, the persisted stack trace does not contain the potentially sensitive original message. If root-cause investigation is needed, use a **permissioned, redacted diagnostic channel with limited retention**; do not automatically send raw exceptions to general logs.

**Do not catch all exceptions and return normally**: that can produce `exitCode=0` despite a business failure. Throw an exception with a safe message or use a mechanism that returns an appropriate failure exit code for the Task; security must not falsify execution status.

### 7.2. Listener Writing a Structured exitMessage

A listener can record a concise final message so operators understand the task outcome:

~~~java
import org.springframework.cloud.task.listener.annotation.FailedTask;
import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.stereotype.Component;

@Component
public class SafeFailureSummaryListener {

    @FailedTask
    public void onFailure(
            TaskExecution execution, Throwable failure) {
        execution.setExitMessage(
                "FAILED; reason=TASK_EXECUTION_ERROR");
    }
}
~~~

**Scope of the listener:** `exitMessage` is under your control; it **does not automatically sanitize `errorMessage`**, which the framework can write from the exception. You must coordinate exception control at the **originating source**, rather than expecting a final listener to redact everywhere.

Do not set `@AfterTask` to unconditionally write `SUCCESS`: that callback can run after a failure and overwrite the message set by `@FailedTask`. If you have a summary listener, only record success when the status is actually successful.

## 8. Spring Batch JobParameters Must Also Be Treated as Controlled Public Metadata

When a Task runs a Spring Batch Job, `JobParameters` are stored in **JobRepository**, typically in `BATCH_JOB_EXECUTION_PARAMS`. Good example:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-23", true)
        .addString("partnerId", "partner-a", true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();
~~~

Do not do this:

~~~java
// DO NOT PUT secrets into JobParameters, even with identifying=false.
JobParameters bad = new JobParametersBuilder()
        .addString("apiToken", apiToken, false)
        .toJobParameters();
~~~

**`identifying=false` does not mean a parameter is hidden or not written to the DB**. It only excludes the parameter from identifying the `JobInstance`. On restart, Spring Batch needs JobParameters metadata; therefore, they typically outlive the process and are exposed by various Batch Explorer/UI tools.

Better approach:

- JobParameters hold `partnerId` or a safe `credentialRef`.
- The `ItemReader`/service fetches the token at runtime via a secret provider.
- Do not put tokens into the Job/Step `ExecutionContext`, because `ExecutionContext` can also be **serialized to JobRepository** for checkpointing/restart.
- Avoid letting DTOs/Items/exceptions hold tokens in state that gets serialized or logged.

Distinguish `TaskRepository` from `JobRepository`: **the two metadata stores have different roles**, and read permissions/backup protection must be configured for both if the application uses Spring Batch.

## 9. Redaction Mechanisms in Logs and Tracing

Do not try to solve this problem with **a single regex filter** because secret formats are not fixed. Use multiple layers:

1. **Avoid generating values that need redacting:** do not put secrets into arguments, exceptions, log messages, metric tags, or span attributes.
2. **Allowlist logging:** log only `event`, `operation`, `outcome`, reason codes, processed counts, and safe correlation IDs.
3. **Centralized sanitization:** configure logging/HTTP clients to mask `Authorization`, `Cookie`, `Set-Cookie`, `X-Api-Key`, and sensitive URL strings; treat this as a secondary barrier.
4. **Do not log raw request/response bodies:** if debugging is needed, use synthetic/sample data, strip sensitive fields, and restrict viewing permissions.
5. **Protect tracing:** do not put bearer tokens, passwords, signed URLs, or raw queries into `Span` attributes; choose low-cardinality tags for metrics.
6. **Permission and retention policies:** log, trace, and event backends must have ACLs, retention periods, access audits, and encryption matching the data classification.

### 9.1. Example Safe Logging Interceptor

~~~java
// Pseudocode at the HTTP client boundary:
log.info(
    "partner_request_completed operation={} statusCode={} durationMs={}",
    "import-orders",
    response.statusCode(),
    duration.toMillis());

// Do not do:
// log.info("headers={}", request.headers());
// log.info("body={}", response.body());
// log.info("url={}", request.uri());
~~~

URLs may contain query tokens. When HTTP target observability is needed, log an **allowlisted host/route template** instead of the full URI. For HTTP clients/SDKs, check library debug loggers because not logging in your own code **does not guarantee the library isn't logging either**.

### 9.2. Do Not Put Tokens in Metric Labels

~~~text
# Recommended:
business.task.outcome{operation="import",outcome="success"}

# Not recommended:
business.task.outcome{apiToken="<secret>",customerEmail="<PII>"}
~~~

Metric labels often have long retention and are broadly indexed/queried. Beyond leaks, labels that vary per request cause **high cardinality**. Put `TaskExecution ID` into structured logs/traces or metadata, rather than using it as a metric label for every run.

## 10. Spring Boot Actuator: Protecting Configuration Views

Although Tasks usually run with `spring.main.web-application-type=none` and do not open an HTTP server, some applications still enable **Actuator** or JMX. The `/actuator/env` and `/actuator/configprops` endpoints can contain sensitive configuration.

In Spring Boot 3.x, these endpoints **mask values by default**, and the `management.endpoint.env.show-values`/`management.endpoint.configprops.show-values` properties control visibility. Example of a strict configuration:

~~~yaml
management:
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
  endpoints:
    web:
      exposure:
        include: "health,info"
~~~

This is a **secondary defense layer**, not a way to stop Spring Cloud Task from saving arguments. Never enable `show-values: always` in production just for debugging. If management endpoints are needed, protect the network, TLS, authentication, and authorization; audit JMX and custom endpoints as well.

**Do not assume Actuator sanitization also applies** to `TASK_EXECUTION_PARAMS`, `BATCH_JOB_EXECUTION_PARAMS`, structured logs, or exception messages. They are separate data paths.

## 11. Access Control for TaskRepository and JobRepository

Anyone with read access to metadata can view parameter and error history. Therefore:

| Principal | Recommended Permissions | Reason |
| --- | --- | --- |
| Task runtime account | Required DML permissions for Task tables (and Batch if applicable) | Create/update the result of a run |
| Orchestrator / Task explorer | Required read permissions for metadata | View status without needing DB admin privileges |
| Operations support | Restricted read access through a controlled UI | Avoid accessing raw arguments/errorMessage beyond operational need |
| Migration account | DDL through an approved change process | Do not grant broad `CREATE/ALTER/DROP` permissions to runtime |
| Backup / BI / export | Least privilege, encryption, and retention limits | Metadata may contain previously leaked data |

**Do not use `SELECT *` to paste raw arguments or errors tables into tickets** without controlling the contents. When sharing incident details, export only allowed fields such as execution ID, task name, timestamps, exit code, and sanitized reason code.

When TaskRepository is shared across multiple teams or tenants, design **access segregation** via appropriate roles/schemas/orchestration tools. **An account with `SELECT` on `TASK_EXECUTION_PARAMS` can read parameters from many runs**; UI masking does not help if the account still has direct SQL access.

### 11.1. Minimal Status-Only Query

~~~sql
SELECT TASK_EXECUTION_ID,
       TASK_NAME,
       START_TIME,
       END_TIME,
       EXIT_CODE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'partner-import-task'
ORDER BY START_TIME DESC;
~~~

The query above **omits** `TASK_PARAM`, `EXIT_MESSAGE`, and `ERROR_MESSAGE`; it is better suited for broad status reporting. To investigate detailed failures, use an authorized workflow with controlled data output.

### 11.2. Retention, Backups, and Purging Old Data

Metadata may be kept for months or years for investigation and restarts. If a token was once accidentally written to `TASK_EXECUTION_PARAMS`, fixing the code **only prevents future leaks**; old copies may remain in:

- TaskRepository/JobRepository tables.
- Database backups, replicas, CDC streams.
- Log shippers, search indexes, dashboard snapshots.
- CI/CD job logs and diagnostic archives.
- Tickets/screenshots created by operators.

In an actual leak, **revoke/rotate the secret first**, assess access scope, and follow the incident response process. Then perform cleanup consistent with retention, FK relationships, restart requirements, and backup lifecycles. Do not directly delete Task/Batch tables for a “quick wipe,” as that can destroy history required for recovery.

## 12. Verifying No Leaks Using a Fake Canary Token

Use a **fake canary** instead of a real secret during testing:

~~~text
SCT_CANARY_FAKE_TOKEN_FOR_TEST_20261124
~~~

This is a string with **no authentication value**, used to detect leak paths. Supply it via a test Secret, **not** via arguments. Run a test Task where the service receives the fake value without making sensitive external calls.

Verification:

1. Launch the Task with `--business-date=...` and `--partner-id=...`, **with no token in argv**.
2. Confirm `TaskExecution.arguments` contains only allowlisted options.
3. Verify `TASK_EXECUTION_PARAMS` does not contain the canary.
4. If Batch is used, verify `BATCH_JOB_EXECUTION_PARAMS` and `ExecutionContext` do not contain the canary.
5. Verify `EXIT_MESSAGE` and `ERROR_MESSAGE` do not contain the canary in both success and failure scenarios.
6. Search for the canary in logs/traces/events emitted from the process using appropriately authorized test tooling.
7. Verify the Pod/Job spec contains no token in `args` or `env[].value`; only `secretKeyRef` references exist.
8. Simulate an HTTP error whose message contains the canary; confirm the final error code is sanitized and the Task still fails properly.
9. Audit ServiceAccount/operator permissions to view metadata and Secrets under least privilege.

### 12.1. Test SQL Without Displaying Raw Data

Example for a **test environment**, using the fake marker to count occurrences in Task arguments:

~~~sql
SELECT COUNT(*) AS task_parameter_canary_hits
FROM TASK_EXECUTION_PARAMS
WHERE TASK_PARAM LIKE '%SCT_CANARY_FAKE_TOKEN_FOR_TEST_20261124%';
~~~

Expect **0 rows containing the canary**. Do not put a real password into a query to “test whether it leaked”: the SQL query itself, database audit logs, and console history can create **a new leak path**.

For Spring Batch 5.x:

~~~sql
SELECT COUNT(*) AS job_parameter_canary_hits
FROM BATCH_JOB_EXECUTION_PARAMS
WHERE PARAMETER_VALUE
      LIKE '%SCT_CANARY_FAKE_TOKEN_FOR_TEST_20261124%';
~~~

Column names vary across Spring Batch generations; check the deployed DDL. For `ERROR_MESSAGE`, you can similarly count matches in `TASK_EXECUTION`, without printing full stack traces to the screen before verifying the data.

### 12.2. Failure Test Scenario

Intentionally simulate an API client throwing an exception containing the canary:

~~~text
Remote response (test-only):
  "Authorization failed for token:
   SCT_CANARY_FAKE_TOKEN_FOR_TEST_20261124"
~~~

If the application simply executes `throw ex;`, the framework may write the raw exception into `ERROR_MESSAGE`. Under a safe error-handling policy, the application must **translate it into a clean reason code** such as `PARTNER_AUTH_REJECTED` so the Task status still fails without putting the token into metadata.

**Do not test only the happy path.** Leaks commonly happen specifically during timeouts, HTTP 401/403 responses, JDBC errors, data parsing failures, or when a logger is switched to `DEBUG`.

## 13. Operating with Rotation and Task Lifetimes

An advantage of a finite Task is that **each run can fetch a fresh secret** at startup. However, this is only safe if the secret delivery mechanism has a proper lifecycle.

| Scenario | Design Consideration |
| --- | --- |
| Token rotated between two schedules | The new run fetches the current version; the old one is revoked per procedure |
| Token expires mid-Task during a long run | The client has token refresh / credential provider support or safe retry |
| Pod retries within the same Kubernetes Job | The new Pod fetches the appropriate secret while preserving the processing period's **business key** |
| Secret revoked due to suspected leak | Block the old credential at the issuer, inspect in-flight runs, issue a new one |
| Mounted Secret changes while Pod is running | The application must re-read/refresh via supported mechanisms; do not assume updates apply everywhere automatically |
| Protecting DB password | TaskRepository permissions, TLS to DB, rotation and connection change coordination |

If rotation causes an import run to fail, handle retries/idempotency using the business key, **never using an old token saved in TaskExecution.arguments for a “quick recovery”**. Execution metadata should be sufficient to reconstruct **business intent**, not contain credentials to reconstruct **access privileges**.

## 14. Common Pitfalls

| Symptom | Root Cause | Resolution |
| --- | --- | --- |
| Token exposed in `TASK_EXECUTION_PARAMS` | Passed via `--api-token` | Move to Secret/env/file, rotate the exposed credential |
| Token absent from Task arguments but present in Batch repository | Token copied into `JobParameters` | Pass only business keys; fetch token at runtime |
| `ERROR_MESSAGE` contains a signed URL | Original exception included the URL/token | Do not propagate raw messages; use sanitized reason codes |
| `EXIT_MESSAGE` contains customer data | Listener wrote `failure.getMessage()` | Persist only status and safe error codes |
| Logs leak `Authorization` header | HTTP client logging interceptor or library DEBUG level | Disable raw headers/bodies, use allowlisting and redaction |
| Secrets committed in YAML | Used `env.value` or manifests containing base64 | Use Secret references/secret manager; scrub git history and rotate |
| Dashboard readers can view old tokens | Unprotected metadata | Review RBAC, DB grants, UI permissions, retention |
| Using `identifying=false` to “hide” a Batch token | Misunderstanding JobParameters | Never put tokens in JobParameters under any flag |
| Passwords exposed via Actuator | Enabled `show-values=always` or unprotected custom endpoint | Enable sanitization, restrict endpoints and authorization |
| Cannot determine root cause after redaction | Only a very generic reason code remains | Add correlation IDs, restricted-access diagnostic store, and support rules |
| Task `COMPLETED` despite API failure | Code caught exception and returned normally | Propagate sanitized error, verify exit code |
| Rotation completed but logs/backups still hold old token | Leak existed before code fix | Revoke token, follow incident/retention/backup procedures |

## 15. Hands-On Exercise

A system runs `daily-payment-import-task` via a Kubernetes CronJob. The task accepts `--business-date`, `--partner-id`, calls a partner API with a **bearer token**, saves records, and runs a Spring Batch Job. The operations team wants support staff to see status in the dashboard without **being able to view credentials**.

**Part A — Classify and Fix the Launch:**

1. Mark which fields are safe to persist: `business-date`, `partner-id`, `partner-api-token`, `source-id`, `credential-ref`.
2. Rewrite Pod `args` to keep only permitted parameters; supply the token via `secretKeyRef` or a mounted secret file.
3. Configure `spring.datasource.password` via an environment variable without putting the password into `--spring.datasource.password`.
4. Explain why `TASK_EXECUTION_PARAMS` can still contain secrets if launched via CLI/SCDF even if the application never calls `log.info`.

**Part B — Java Code and Metadata:**

5. Write a runner that logs only `event, businessDate, outcome, acceptedCount`, without printing `ApplicationArguments` or `Environment`.
6. Convert `PartnerAuthenticationException` into a **safe exception message** while still failing the Task.
7. Write a `@FailedTask` listener that sets `exitMessage="FAILED; reason=PARTNER_AUTH_REJECTED"` or a classified reason code; explain why the listener does not automatically sanitize `ERROR_MESSAGE`.
8. Build Batch `JobParameters` without the token; explain why `identifying=false` is not a hiding mechanism.

**Part C — Verification and Operations:**

9. Use the fake canary `SCT_CANARY_FAKE_TOKEN_FOR_TEST_20261124` and run both success and error paths.
10. Verify TaskRepository, JobRepository, logs, and traces do not contain the canary; return only **match counts** instead of dumping values.
11. Design status-only read permissions for operators and restricted raw error viewing for the incident team.
12. Describe the procedure when a real token is found to have entered TaskExecution: revoke/rotate, scope assessment, cleanup, and backfill/backup investigation.

**Pass Criteria:** across all test cases, no credentials appear in argv, Task/Batch metadata, logs, metrics, traces, or messages; the task still reports failure properly via exit code; permissions and incident response procedures are defined upfront.

## 16. Summary

1. **`TASK_EXECUTION_PARAMS` persists arguments**, so **do not pass secrets via CLI**, even under Spring Boot property names or through a launcher.
2. **`BATCH_JOB_EXECUTION_PARAMS` persists JobParameters**; `identifying=false` neither hides nor prevents persisting the value.
3. **`ERROR_MESSAGE` can contain stack traces**, and **`EXIT_MESSAGE` is set by listeners**. Protect sensitive information at the **exception origin** and do not copy raw messages.
4. **Use arguments for traceable business data**, use Secret/env/mounted files/secret managers for credentials, and restrict read permissions.
5. **Kubernetes Secret base64 is not encryption**; enable encryption at rest, minimal RBAC, never commit secret manifests, and control debug and backup access.
6. **Never log entire args, Environment, HTTP headers, bodies, or config DTOs**. Use allowlists, reason codes, and safe correlation IDs.
7. Protect Actuator, logs, traces, metrics, and metadata reporting systems **independently**, without relying on one filter covering every data path.
8. **Test with a fake canary**, covering success paths, exceptions, retries, and log sinks; never use a real secret as a search string.
9. When a leak has occurred, **rotate/revoke the credential first** and handle all copies existing in repositories, backups, logs, and tickets according to incident response.

### Official References

- [Spring Cloud Task — Features and TaskRepository](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Cloud Task — Task Repository Schema](https://docs.spring.io/spring-cloud-task/reference/appendix-task-repository-schema.html)
- [Spring Batch — Metadata Schema and JobParameters](https://docs.spring.io/spring-batch/reference/schema-appendix.html)
- [Spring Boot — Actuator Endpoints and Sanitization](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html)
- [Kubernetes — Good Practices for Secrets](https://kubernetes.io/docs/concepts/security/secrets-good-practices/)
- [Kubernetes — Using Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
- [Kubernetes — Security Checklist](https://kubernetes.io/docs/concepts/security/security-checklist/)
