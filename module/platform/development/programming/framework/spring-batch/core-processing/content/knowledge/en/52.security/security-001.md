# Secrets in JobParameters — Security for Spring Batch Core Processing

## 1. Why must secrets not be passed via JobParameters?

In Spring Batch, `JobParameters` identify a batch job and provide inputs such as the processing date, tenant, data source, or filename. When a Job needs to connect to an external API or system, developers sometimes pass a password, API key, OAuth token, or private key into `JobParameters`:

~~~java
// Bad example: the token may be stored in JobRepository and logs.
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16")
    .addString("apiToken", "dummy-sensitive-token")
    .toJobParameters();
~~~

**JobParameters are execution metadata, not a secret store.** With a JDBC JobRepository, parameter values are persisted to support JobInstance identification and JobExecution history management. In many execution paths, parameters also appear in logs, dashboards, operational reports, database dumps, or backups.

In particular, switching to `.addString("apiToken", token, false)` **does not make the secret any safer**. The `identifying=false` flag only excludes the parameter from the JobInstance identity; it does not instruct Spring Batch to mask logs, encrypt it, or skip persistence.

Lesson objectives:

- Understand identifying parameters and the data flow in JobRepository.
- Recognize leaks from metadata, logs, ExecutionContext, REST APIs, and monitoring.
- Use business keys or non-sensitive references to retrieve secrets at runtime.
- Build a Step that uses a secret manager with the appropriate scope and permissions.
- Handle rotation, retry, and restart without embedding credentials in metadata.
- Test against secret leaks, protect multi-tenant isolation, and handle secrets that were accidentally persisted.

## 2. JobInstance, JobExecution, and identifying parameters

~~~text
Job: importOrdersJob
Identifying parameters:
    businessDate = 2026-11-16
    tenantCode   = acme
                |
                v
          JobInstance #42
             /       \
            v         v
   JobExecution #101  JobExecution #102
        FAILED           COMPLETED
                         (restart)
~~~

Spring Batch identifies a JobInstance by **the Job name and the set of identifying JobParameters**. If a Job is FAILED and restarted, the new execution belongs to the same JobInstance. If an identifying parameter changes, the framework creates a different JobInstance.

Appropriate parameters:

~~~java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16", true)
    .addString("tenantCode", "acme", true)
    .addString("requestedBy", "scheduler", false)
    .toJobParameters();
~~~

| Parameter | Should pass? | Explanation |
| --- | --- | --- |
| `businessDate` | Yes | Business processing period, stable across restarts. |
| `tenantCode` | Conditionally | May require restricting metadata read permissions by tenant. |
| `inputId` | Conditionally | Prefer an opaque ID or an approved path. |
| `credentialRef` | Conditionally | Only when the reference is non-sensitive and access-controlled. |
| Password, API key, refresh token | **No** | Credentials may be persisted and logged. |
| Private key, signing key | **No** | Secrets must be managed by an appropriate secret store. |
| JDBC URL with password | **No** | Contains credentials embedded in the string. |

Do not use a token or a token hash as an identifying parameter. When a token is rotated, the JobInstance identity should not change; the data period is still the same batch.

## 3. Where can secrets leak?

~~~text
      Scheduler / REST / CLI
              |
              v
         JobParameters
              |
        +-----+---------+
        |     |         |
        v     v         v
   JobRepo   Logs    Admin/Monitoring
        |     |         |
        v     v         v
    BATCH_*  Log DB    Dashboard/APM
        |     |         |
        +-----+---------+
              |
              v
        Backup / Export
~~~

| Leak vector | Risk |
| --- | --- |
| JDBC metadata | JobParameter values reside in metadata tables and can be queried by DBAs/reporting services. |
| `JobParameters.toString()` | Logs contain all keys/values. |
| REST request | Credentials in the body/query may appear in gateways, reverse proxies, or access logs. |
| CLI | Argument values may appear in process listings and shell history. |
| `ExecutionContext` | If a token is stored in Job/Step context, the serializer may persist it. |
| Actuator/APM | Environment, request attributes, traces, or exception messages contain secrets. |
| Metrics | Attaching a token as a tag both leaks it and causes very high cardinality. |
| Backup/snapshot | Secrets persist even after the original Job and token have expired. |

In Spring Batch **5.x**, the `BATCH_JOB_EXECUTION_PARAMS` table typically has:

~~~text
JOB_EXECUTION_ID
PARAMETER_NAME
PARAMETER_TYPE
PARAMETER_VALUE
IDENTIFYING
~~~

Spring Batch 4.x and other versions may use a different schema. Do not copy SQL statements that modify metadata without checking the schema and its relationship with the JobInstance key.

To check suspicious parameter names **without printing values**:

~~~sql
SELECT JOB_EXECUTION_ID, PARAMETER_NAME, IDENTIFYING
FROM BATCH_JOB_EXECUTION_PARAMS
WHERE LOWER(PARAMETER_NAME) IN (
    'password', 'apikey', 'api_token',
    'accesstoken', 'access_token', 'clientsecret'
);
~~~

This is only a preliminary screening step: a secret may be hidden inside JSON under a `config` key, and a `credentialRef` parameter might simply be an allowed reference.

## 4. Secure architecture: resolve secrets inside the Step

Instead of passing raw secrets, the launcher only sends business IDs:

~~~text
Scheduler / Controller
    |
    | businessDate=2026-11-16
    | tenantCode=acme
    v
JobRepository
    |
    | No password/token
    v
StepScope Tasklet / Writer
    |
    | tenantCode
    v
CredentialResolver
    |
    +--> Server-side tenant mapping
                  |
                  v
          Secret Manager / Vault
                  |
                  v
              Credential
                  |
                  v
            API / DB client
~~~

Two implementation approaches:

1. **Business key → server-side mapping:** The Job receives `tenantCode=acme`, and the application maps it to a secret identifier in server-side security configuration. This is the preferred option when clients must not choose credentials themselves.
2. **Secret reference:** The Job receives `credentialRef=partners/acme/token`, and the Step retrieves the actual value from the secret store. Apply this only when the reference itself is not classified as confidential and access permissions have been verified.

A secret reference can also disclose customer names or environments. If the path is sensitive, use an opaque ID or business key and keep the path out of JobParameters.

### Secret storage sources

| Source | Usage | Things to verify |
| --- | --- | --- |
| HashiCorp Vault | Retrieve KV or dynamic credentials | Token policy, TTL, audit, and rotation. |
| AWS Secrets Manager | IAM role retrieves secret | Per-workload permissions; do not embed access keys in the Job. |
| Google Cloud Secret Manager | Workload identity/service account | Permissions for the exact resource and secret version. |
| Azure Key Vault | Managed identity | Minimal read permissions for secrets/certificates. |
| Kubernetes Secret | File mount or environment | RBAC, etcd encryption, container access, and secret rotation. |
| Dedicated token issuer | Issue short-lived tokens | Expiration, refresh, and bounded retry count. |

Prefer **workload identity** rather than creating another static master password for the application to access the secret manager.

## 5. Spring Batch 5.2 example: Tasklet fetching a secret at runtime

Assume the application uses Spring Boot 3.x, Spring Batch 5.2.x, and Java 17+. Define the application interfaces:

~~~java
public interface CredentialResolver {
    // Implementation reads the token based on tenant and workload permissions.
    char[] resolvePartnerToken(String tenantCode);
}

public interface PartnerGateway {
    // Client must not log or persist the token.
    void synchronize(String tenantCode, String businessDate, char[] token);
}
~~~

The Tasklet is instantiated per StepExecution with non-sensitive JobParameters:

~~~java
import java.util.Arrays;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class PartnerBatchConfiguration {

    @Bean
    @StepScope
    Tasklet partnerTasklet(
            CredentialResolver resolver,
            PartnerGateway gateway,
            @Value("#{jobParameters['tenantCode']}") String tenantCode,
            @Value("#{jobParameters['businessDate']}") String businessDate) {

        return (contribution, chunkContext) -> {
            char[] token = resolver.resolvePartnerToken(tenantCode);
            try {
                gateway.synchronize(tenantCode, businessDate, token);
                return RepeatStatus.FINISHED;
            } finally {
                Arrays.fill(token, '\0');
            }
        };
    }
}
~~~

Step and Job configuration:

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step partnerStep(
        JobRepository repository,
        PlatformTransactionManager tx,
        Tasklet partnerTasklet) {
    return new StepBuilder("partnerStep", repository)
            .tasklet(partnerTasklet, tx)
            .build();
}

@Bean
Job partnerJob(JobRepository repository, Step partnerStep) {
    return new JobBuilder("partnerJob", repository)
            .start(partnerStep)
            .build();
}
~~~

`char[]` allows clearing the buffer owned by your code, though an HTTP client or SDK may create `String` copies, so you should not claim that secrets can be completely scrubbed from the heap. Do not write tokens into exceptions, logs, or mutable singleton fields shared across tenants/Jobs.

For a chunk-oriented Step, the resolver can reside in the HTTP client or item writer. Caching and TTL-based refresh are needed if the Step runs for a long time, alongside authorization checks and avoiding excessive load on the secret manager. Do not move refresh tokens into JobParameters to reduce resolve calls.

## 6. Blocking credentials at request ingress

A common mistake is accepting an arbitrary parameter map and building JobParameters from it:

~~~java
// Bad practice: callers can send any key/value.
for (Map.Entry<String, String> entry : rawRequest.entrySet()) {
    builder.addString(entry.getKey(), entry.getValue());
}
~~~

Replace it with an allowlist DTO:

~~~java
public record ImportRequest(
        String businessDate,
        String tenantCode) {
}

JobParameters parametersFor(ImportRequest request) {
    return new JobParametersBuilder()
            .addString("businessDate", request.businessDate(), true)
            .addString("tenantCode", request.tenantCode(), true)
            .toJobParameters();
}
~~~

Before building parameters, the API must authenticate the caller, verify permission to run the Job for the tenant, and validate that `businessDate` matches the expected format. Do not allow callers to arbitrarily specify another tenant's secret path.

### JobParametersValidator as an additional safeguard

~~~java
import java.util.Locale;
import java.util.Set;

import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.batch.core.JobParametersValidator;

public final class NoRawSecretsValidator
        implements JobParametersValidator {

    private static final Set<String> FORBIDDEN = Set.of(
        "password", "passwd", "apikey", "api_key",
        "accesstoken", "access_token", "clientsecret",
        "client_secret", "privatekey");

    @Override
    public void validate(JobParameters parameters)
            throws JobParametersInvalidException {
        for (String name : parameters.getParameters().keySet()) {
            if (FORBIDDEN.contains(name.toLowerCase(Locale.ROOT))) {
                throw new JobParametersInvalidException(
                    "Raw credentials are forbidden in JobParameters");
            }
        }
    }
}
~~~

Register it with `.validator(new NoRawSecretsValidator())` in `JobBuilder`. This validator is useful, **but it is not the primary control**: it does not catch secrets placed under other names such as `options` or `config`. Depending on the launcher path and version, some metadata handling/logging may occur before Job-level validation runs. Perform input validation at the boundary before passing values into Batch.

## 7. Do not store secrets in ExecutionContext

The following approach is still dangerous:

~~~java
// Wrong: Step ExecutionContext may be serialized into the database.
stepExecution.getExecutionContext()
    .putString("partnerToken", token);
~~~

Spring Batch uses `ExecutionContext` to store Job/Step checkpoints; a JDBC JobRepository may persist it into `BATCH_JOB_EXECUTION_CONTEXT` and `BATCH_STEP_EXECUTION_CONTEXT`.

Store non-secret values for recovery:

~~~java
stepExecution.getExecutionContext()
    .putString("tenantCode", "acme");
stepExecution.getExecutionContext()
    .putLong("lastProcessedItemId", 1510L);
~~~

On restart, the Step retrieves `tenantCode` and requests a fresh secret from the resolver. Do not put passwords, refresh tokens, access tokens, private keys, or connection strings containing passwords into the context.

Some encryption/decryption workflows need to pin a **key version**. In that case, a non-sensitive version ID may be stored per policy so the secret manager supplies the matching key version; never store raw key bytes.

## 8. Rotation, expiration, and restart

~~~text
02:00  JobExecution #101 uses token version A
02:20  JobExecution #101 FAILED
02:30  Secret manager rotates to version B
03:00  JobExecution #102 restarts same JobInstance
~~~

If token A were stored in JobParameters, it could expire while still remaining in metadata. With a runtime resolver, execution #102 can obtain token B, provided changing the token does not alter business semantics.

| Scenario | Strategy |
| --- | --- |
| Token used only for API authentication | Resolve the latest credential at runtime. |
| Token TTL shorter than Job duration | Client/resolver performs refresh with bounded retries. |
| Key used to decrypt historical data | Pin an allowed version reference and retain versions per retention policy. |
| Secret revoked urgently | Rotate/revoke in the secret store without changing the JobInstance identity. |
| Restart on another node | The new node uses workload identity and corresponding permissions. |

Do not use a token or token hash as an identifying parameter: rotation will mutate the JobInstance identity and may cause the system to reprocess from the beginning.

## 9. Preventing leaks via logs, metrics, and tracing

~~~java
// Log only approved metadata.
log.info("Starting job={} businessDate={} tenant={}",
        "partnerJob", businessDate, tenantCode);

// Avoid logging raw JobParameters, Authorization headers,
// request bodies containing tokens, secret values, or URLs with tokens.
~~~

Review:

- Logging frameworks, schedulers, Quartz, and CI runners.
- `toString()` of JobParameters, request DTOs, and SDK credentials.
- HTTP headers: Authorization, Cookie, X-API-Key.
- Exception messages and structured log fields.
- APM traces, request/response capture, and SQL bind parameters.
- Actuator `env`, `configprops`, heap dumps, and support bundles.
- Dashboards and database metadata exports.

Metrics should use low-cardinality fixed tags such as job, step, status, and failure category. Do not attach raw tokens, sensitive credential paths, or per-request unique identifiers to Prometheus labels.

### Securing metadata access

Even without raw secrets, JobParameters may still contain tenant names, filenames, or transaction timestamps. Protect read access to `BATCH_*`, encryption at rest, TLS, retention, and backup access. Disk encryption only protects one layer; users authorized to read decrypted data can still inspect metadata.

## 10. Testing against secret leaks

### 10.1. Verifying clean JobParameters

~~~java
JobParameters params = new JobParametersBuilder()
        .addString("businessDate", "2026-11-16", true)
        .addString("tenantCode", "acme", true)
        .toJobParameters();

assertFalse(params.getParameters().containsKey("apiToken"));
assertFalse(params.getParameters().containsKey("password"));
assertFalse(params.getParameters().containsKey("clientSecret"));
~~~

This test only checks a single builder; you also need tests for the actual launch paths from REST/CLI/scheduler. If the parser accepts arbitrary key/value pairs, callers can still bypass it using different keys.

### 10.2. Verifying JDBC metadata

In an integration test with Spring Batch 5.x and a JDBC JobRepository:

~~~java
List<String> parameterNames = jdbcTemplate.queryForList(
    "SELECT PARAMETER_NAME " +
    "FROM BATCH_JOB_EXECUTION_PARAMS " +
    "WHERE JOB_EXECUTION_ID = ?",
    String.class,
    jobExecution.getId());

assertTrue(parameterNames.contains("businessDate"));
assertTrue(parameterNames.contains("tenantCode"));
assertFalse(parameterNames.contains("apiToken"));
assertFalse(parameterNames.contains("password"));
~~~

Query **only the names** so secret values are never accidentally printed into test reports. Use the exact schema for your project's Batch version.

### 10.3. Testing resolver, rotation, and multi-tenancy

1. Use a fake CredentialResolver returning test token A.
2. Run the Job with `businessDate` and `tenantCode`, and make the Step fail at a deterministic point.
3. Switch the fake token to B and restart the **same JobInstance**.
4. Verify that the JobInstance ID is unchanged, the JobExecution ID is new, and the final data is accurate.
5. Check that raw tokens A/B do not appear in JobParameters, ExecutionContext, logs, or traces.
6. Have a tenant A caller request tenant B's credentials; both the API and the resolver must reject it.

Integration tests use `@SpringBatchTest` and a JDBC JobRepository to observe real metadata. Do not delete `BATCH_*` tables between the FAILED run and restart; never use production credentials in tests.

## 11. When a secret has already been persisted in JobRepository

If a real credential is discovered in metadata tables, simply deploying new code does not remove historical copies.

Remediation process:

1. **Stop further exposure:** remove raw secrets from APIs/launchers, disable sensitive logging paths, and roll out an allowlist.
2. **Assess the scope:** determine which JobExecutions, metadata DBs, log backends, dashboards, traces, backups, and snapshots may contain the credential.
3. **Restrict access:** block reporting accounts or endpoints that do not need to view this data.
4. **Rotate/revoke** exposed credentials according to risk severity.
5. **Check incomplete JobInstances:** altering old parameters can affect the restartability of batches that have already committed data.
6. **Plan redaction/migration** for metadata, logs, and backups according to the schema and retention policy; test in an isolated environment first.
7. **Prevent regression:** update tests, code reviews, and logging rules.

**Do not manually edit/delete the `PARAMETER_VALUE` column or truncate `BATCH_*` tables in production** just to scrub a secret. JobRepository relies on metadata to identify JobInstances and recover executions; inconsistent edits can lose checkpoints or cause duplicates.

Tokens remaining in backups remain a risk even after the live database has been cleaned. Rotating/revoking reduces the exploitability of old copies, while backup access must still be controlled.

## 12. Spring Batch 5.2 and 6.x

| Item | Spring Batch 5.2.x | Spring Batch 6.x |
| --- | --- | --- |
| JobParametersBuilder | `org.springframework.batch.core.JobParametersBuilder` | Domain types are organized into packages such as `org.springframework.batch.core.job.parameters`. |
| Launching a Job | `JobLauncher.run(Job, JobParameters)` | `JobOperator.start(Job, JobParameters)` is the newer API direction. |
| Tasklet step | `new StepBuilder(name, repo).tasklet(tasklet, tx)` | Use the builder/API appropriate for 6.x. |
| JDBC metadata | `BATCH_JOB_EXECUTION_PARAMS` schema per 5.x | Check 6.x JDBC schema/migrations when deploying. |
| Security principle | Avoid raw secrets in JobParameters/Context | **Unchanged**: still avoid raw secrets and mask logs. |

If a resourceless repository is configured on a given version, the absence of JDBC tables does not prove that passing tokens is safe; credentials still pass through APIs, processes, logs, and memory.

## 13. Common mistakes

**Assuming identifying=false protects a secret.** This flag only affects JobInstance identity.

**Putting a secret into ExecutionContext for a later Step.** The context can be persisted and logged.

**Base64-encoding or storing a token hash as a parameter.** Base64 is not encryption; a token hash is not a business identity and can alter the instance after rotation.

**Letting callers pass an arbitrary secretRef.** Risks cross-tenant access; authorization and server-side mapping must be enforced.

**Redacting only in the frontend.** Values may already exist in the DB, API responses, logs, and backups.

**Holding a token in a mutable singleton field.** Easily leaks across tenants, breaks under concurrent Jobs, and becomes stale after rotation.

**Using environment variables without considering process and diagnostics access.** Credentials still require access controls, masking, retention, and lifecycle management.

**Deleting exposed metadata immediately.** Can break restarts and history; a proper remediation plan is required.

## 14. Hands-on exercises

### Exercise 1 — Comparing metadata

On an isolated test database, pass a **fake token** via JobParameters to observe the metadata persistence risk; refactor the launcher to use `businessDate` + `tenantCode` and confirm the new parameters contain no token.

### Exercise 2 — Tasklet fetching a token at runtime

Create a fake CredentialResolver, a `@StepScope` Tasklet, and a fake PartnerGateway. Run the Job to completion and verify the token does not appear in JobParameters/ExecutionContext.

### Exercise 3 — Input allowlist

Build a REST controller that accepts only `businessDate` and `tenantCode`; try sending `password`, `apiKey`, `accessToken`, and JSON containing a token. The API must reject them before creating JobParameters and must not log the raw body.

### Exercise 4 — Rotation after failure

Make the first execution fail with fake token A, switch the resolver to token B, and restart the same JobInstance. Verify the same instance ID, a new execution ID, and no duplicate final data.

### Exercise 5 — Multi-tenant isolation

Have a caller authorized for tenant A try submitting tenant B or a `secretRef` belonging to tenant B. Authorization in both the controller and resolver must reject it.

### Exercise 6 — Logging test

Simulate an error in the HTTP client and use log capture to verify the fake credential value does not appear in loggers, exceptions, or traces, while JobExecution ID and failure category remain available for diagnostics.

### Exercise 7 — Already-exposed history

Using a test database, simulate a fake secret stored long ago. Plan rotation, access tightening, backup/log handling, and safe migration before removing metadata history.

## 15. References

- [Spring Batch — Configuring a Job](https://docs.spring.io/spring-batch/reference/job/configuring.html)
- [Spring Batch — Domain Language](https://docs.spring.io/spring-batch/reference/domain.html)
- [Spring Batch — Meta-Data Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html)
- [Spring Batch — Late Binding](https://docs.spring.io/spring-batch/reference/step/late-binding.html)
- [Spring Batch — ItemStream and ExecutionContext](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html)
- [Spring Batch 5.2 — JobParameters API](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/JobParameters.html)
- [Spring Batch 5.2 — JobParametersBuilder API](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/JobParametersBuilder.html)
- [Spring Security Reference](https://docs.spring.io/spring-security/reference/index.html)
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)

