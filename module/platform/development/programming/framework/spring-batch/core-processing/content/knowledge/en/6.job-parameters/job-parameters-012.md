# Protecting Secrets by Not Storing Them Directly in Metadata

Spring Batch stores metadata to identify a JobInstance, track JobExecution and StepExecution, and support restart. JobParameters and ExecutionContext are part of this metadata. Therefore, if you pass a password, API token, private key, or credential directly into JobParameters or ExecutionContext, that value can be written to the repository along with the Job's run history.

The metadata repository is not a secret vault. The safe approach is to keep secrets in a secret management system or the application's secure configuration, and then pass only a non-sensitive reference into the Job when needed. The Step uses that reference to retrieve the secret at execution time.

## 1. Why does Spring Batch metadata need protection?

Spring Batch needs to store state to know whether a Job has run, which Steps have completed, which execution failed, and where it can restart from. The JobRepository stores this information in the metadata store.

The data groups typically stored include:

- The Job name and JobInstance identity information.
- The JobParameters of each JobExecution.
- The status, run time, and exit status of JobExecution and StepExecution.
- The ExecutionContext at Job and Step scope.
- Information for restart and progress tracking.

With a JDBC JobRepository, Spring Batch versions typically use metadata tables with the BATCH_ prefix. For example:

| Data group | Commonly seen metadata table |
|---|---|
| JobInstance | BATCH_JOB_INSTANCE |
| JobExecution | BATCH_JOB_EXECUTION |
| JobParameters | BATCH_JOB_EXECUTION_PARAMS |
| Job ExecutionContext | BATCH_JOB_EXECUTION_CONTEXT |
| StepExecution | BATCH_STEP_EXECUTION |
| Step ExecutionContext | BATCH_STEP_EXECUTION_CONTEXT |

Column names and table structure can differ between Spring Batch versions. The point to remember is that JobParameters and ExecutionContext are durably stored by the repository to support history and restart.

Therefore, if a secret is put into these objects, the secret can appear in the database metadata, backups, exports, admin tools, or monitoring systems that have permission to read the metadata.

## 2. Do not pass secrets directly in JobParameters

An unsafe practice is to put an API key or password into JobParameters:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("apiToken", apiToken, false)
        .toJobParameters();

jobLauncher.run(importOrdersJob, parameters);
~~~

Setting apiToken as non-identifying does not make this value a secret or avoid its being stored in metadata. The identifying flag only determines whether the parameter takes part in identifying the JobInstance. It is not a security flag, does not mask the value, and does not prevent the repository from storing the parameter.

Similarly, you should not put secrets into other JobParameter types, even when the secret is encrypted beforehand at the calling layer but the application decrypts it and stores the clear value somewhere else.

Some data that should not appear in JobParameters:

- Database passwords or service-account passwords.
- API keys, access tokens, refresh tokens, and bearer tokens.
- Private keys, certificate contents with a private key, or passphrases.
- OAuth client secrets.
- Recovery codes, signing keys, and cloud provider credentials.
- Connection strings containing a username/password.
- Any value that lets a reader of the metadata access a system or perform actions on behalf of the application.

JobParameters should contain data describing the work such as the business date, batch code, file ID, tenant, processing mode, or a reference to secure configuration.

## 3. Use a secret reference instead of a secret value

Instead of passing the secret value, pass a name or reference so the application can find the secret in the secret management system.

For example:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("sourceFileId", "file-8421", true)
        .addString("credentialRef", "orders-api/prod", false)
        .toJobParameters();

jobLauncher.run(importOrdersJob, parameters);
~~~

In the example, orders-api/prod is a configuration identifier or secret name in the secret manager. It does not contain the actual credential.

Processing flow:

~~~text
API / Scheduler
      |
      | JobParameters:
      | businessDate, sourceFileId, credentialRef
      v
  JobLauncher
      |
      v
  JobRepository
      |
      | Stores metadata and the reference
      v
  JobExecution
      |
      v
  Step starts
      |
      | Reads credentialRef
      v
  SecretProvider
      |
      | Verifies permission and retrieves the secret
      v
  Secret Manager
      |
      | Returns the secret for the duration of use
      v
  Calls the external service
~~~

The JobRepository only needs to store the reference to identify the configuration to use. The SecretProvider fetches the secret from the secret manager at the time it is needed, and then the processing component uses the secret to authenticate with the target system.

Common secret managers can be provided by a cloud platform, an internal vault system, or an organization's key and credential management service. Choose the provider according to the deployment environment and the application's workload authentication mechanism.

### Designing the reference

A good reference should:

- Not contain a secret or a token that can be used directly.
- Have a stable meaning, be easy to grant permissions on, and easy to manage.
- Only allow access to exactly the secret the Job needs.
- Identify the environment or application, for example orders-api/prod.
- Not reveal sensitive information through its name if many people view the metadata.

Do not use a URL containing a token, a signed URL, a connection string with a password, or a path with embedded credentials as a reference.

If a reference is itself capable of granting access to a secret, for example a bearer token or a signed link, then it is also a secret and must not be stored in metadata.

## 4. Retrieve the secret in the Step at execution time

You can define an abstraction so the Step does not depend directly on a specific secret provider:

~~~java
public interface SecretProvider {
    char[] getSecret(String reference);
}
~~~

An implementation of SecretProvider can call the secret manager's API, use a workload identity, or credentials issued by the deployment environment. Do not hard-code the master key or the secret manager access token in source code.

A Tasklet can receive the reference from JobParameters via Step scope and then retrieve the secret at execution time:

~~~java
@Bean
@StepScope
Tasklet callOrdersApiTasklet(
        @Value("#{jobParameters['credentialRef']}")
        String credentialRef,
        SecretProvider secretProvider,
        OrdersApiClient ordersApiClient) {

    return (contribution, chunkContext) -> {
        char[] secret = secretProvider.getSecret(credentialRef);

        try {
            ordersApiClient.submitPendingOrders(secret);
        } finally {
            Arrays.fill(secret, '\0');
        }

        return RepeatStatus.FINISHED;
    };
}
~~~

Here:

- JobParameters contain only credentialRef.
- @StepScope defers creation of the Tasklet until the Step runs, when the JobParameters are available.
- SecretProvider retrieves the secret by reference.
- The secret is only used within the scope of the operation that needs authentication.
- finally helps clear the contents of the character array after use, within the scope the application controls.

The illustrative code needs to be adapted to the real client API. Some libraries convert the credential to a String or keep a copy in memory; a Java String cannot be reliably cleared. If the client stores the credential internally, consult the library's documentation and limit the client/credential lifecycle appropriately.

Do not put the secret value into exception messages, logs, or content returned from the Tasklet. If retrieving the secret fails, throw an error with safe diagnostic information, such as a non-sensitive reference code and a correlation ID, but do not print the secret value.

### Use a reference from application configuration

If a Job always uses the same secret per environment, you do not necessarily have to put the reference into JobParameters. You can configure an alias in the application configuration and inject it into a bean, while the secret value is still retrieved from the SecretProvider.

Example abstraction:

~~~java
@ConfigurationProperties(prefix = "app.credentials")
public record CredentialProperties(String ordersApiReference) {
}
~~~

Per-environment configuration can contain a non-sensitive alias:

~~~yaml
app:
  credentials:
    orders-api-reference: orders-api/prod
~~~

Then inject CredentialProperties into the Step or a service and call the SecretProvider with the alias. Do not place the secret value directly in a configuration file that is committed to source control. If configuration is obtained from an environment variable or a mounted file, you still need to protect read permissions and avoid printing the entire environment/configuration to logs.

## 5. Non-identifying JobParameters can still be stored

A common misconception is that only identifying JobParameters are stored in metadata. In fact, identifying is the property used to identify the JobInstance. A non-identifying parameter is still part of the JobParameters tied to the JobExecution and can be stored in the repository.

Example:

~~~java
new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("credentialRef", "orders-api/prod", false)
        .toJobParameters();
~~~

In this case:

- businessDate takes part in the JobInstance identity.
- credentialRef does not take part in the JobInstance identity.
- Both can appear in the execution's metadata.

Therefore, marking a parameter non-identifying is only appropriate when you want to change that value without creating a new JobInstance. Do not use this flag to hide a password or token.

Likewise, do not rely on changing the parameter type, renaming the key, or placing a value in a parameter that is not used in the flow to avoid storage. If it is a JobParameter, assume the repository may store that value.

## 6. Do not move secrets into ExecutionContext

ExecutionContext is used to store state needed for restart and to exchange metadata between Steps. The Job ExecutionContext and Step ExecutionContext are also durably stored by the JobRepository.

Therefore, all of the following are unsafe:

~~~java
// Do not do this.
jobExecution.getExecutionContext()
        .putString("apiToken", apiToken);

// Do not do this either.
stepExecution.getExecutionContext()
        .put("databasePassword", databasePassword);
~~~

Do not store secrets in:

- The Job ExecutionContext.
- The Step ExecutionContext.
- A custom execution context key.
- ExitStatus or error description information.
- A custom JobParameter object.
- Execution attributes or self-added metadata that can be persisted.

Instead, only store a reference, a configuration ID, or a non-sensitive secret version if a later Step needs it. When the later Step runs, it retrieves the secret from the SecretProvider by reference.

ExecutionContext suits read positions, last record IDs, file names, checksums, batch codes, and small values that serve restart. It is not a place to store credentials.

## 7. Protecting secrets in logs, exceptions, and monitoring

Even when the secret is not stored in JobParameters, the application can still accidentally expose it through logs or other metadata.

Unsafe examples:

~~~java
log.info("Launching import with parameters: {}", jobParameters);
log.error("API call failed using token " + apiToken, exception);
throw new IllegalStateException("Invalid password: " + password);
~~~

These approaches can put secrets into log aggregation, APM, alerts, exception trackers, or HTTP responses. Log the Job name, the JobExecution ID, the batch code, and the necessary status; do not log the entire parameter map if there is a risk it contains sensitive data.

Example of safer logging:

~~~java
log.info(
        "Launching job={}, sourceFileId={}, businessDate={}, requestId={}",
        "importOrders",
        sourceFileId,
        businessDate,
        requestId
);
~~~

When recording a secret retrieval failure, only provide non-sensitive information:

~~~java
throw new IllegalStateException(
        "Cannot resolve configured credential reference for orders API",
        cause
);
~~~

You also need to control the following places:

- Application and framework logs.
- HTTP access logs and request/response body logging.
- Distributed tracing span attributes.
- Metric labels and dashboards.
- Error tracking and crash reports.
- Audit events.
- Message dead-letter queues.
- Temporary files and dumps when handling errors.

Do not put secrets into metric labels. Metrics usually have broad access and are stored for a long time; only use non-sensitive dimensions such as the Job name, Step, environment, or status code.

## 8. Authorizing access to the secret manager

Using a secret manager is only effective if access permissions are properly restricted.

Grant permissions following the least-privilege principle:

- The order import Job can only read the secrets needed for the orders API.
- The development environment must not read production secrets.
- Developers do not by default need permission to read production secrets just because they can view the source code.
- Each workload or service account has its own identity.
- Permissions to read, update, and rotate secrets are separated where appropriate.
- Secret accesses have audit logs, but the audit logs do not record secret values.

Prefer workload identity or the deployment platform's authentication mechanism for the application to obtain secrets. If a bootstrap credential is needed, that credential must also be provisioned and protected through the environment's secret management mechanism.

Do not place the secret manager's master credential in JobParameters, ExecutionContext, source code, or a committed YAML file.

## 9. Restart and the secret lifecycle

A restart creates a new JobExecution for the same JobInstance when the state and configuration allow. Therefore, you need to decide which secret the restarted Step will use.

There are two common management approaches:

**Use an alias that points to the current secret.** A reference like orders-api/prod always points to the active version. On restart, the Step can receive the latest credential. This is convenient when secrets are rotated frequently, but you must ensure the new credential still has permission and is compatible with the work being continued.

**Use a reference to a specific version.** If the secret manager supports versioned secrets, you can use an alias together with a non-sensitive version code so the Step gets the exact version. This makes the restarted execution's behavior more stable when it needs to complete the same batch of work.

For example, the JobParameters can contain:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("credentialRef", "orders-api/prod", false)
        .addString("credentialVersion", "version-17", false)
        .toJobParameters();
~~~

credentialVersion here is just a version identifier, not a credential. It can still be stored in metadata, so only use it if the version code is non-sensitive.

If you want to keep the behavior unchanged on restart, you must pass the same reference and the appropriate version again. Do not automatically create a new JobInstance just because the secret has been rotated; distinguish changing the credential used to access a service from changing the business unit of work.

If the old secret version has been revoked because of a security incident, the safety requirement must take priority. In that case, the Job may need to stop and be reprocessed under business policy instead of trying to reuse a revoked credential.

## 10. Is encrypting the database metadata enough?

Encrypting the database or disk at rest is a useful layer of protection. It reduces risk when storage devices, snapshots, or backups are accessed without authorization. However, encryption at rest does not turn the metadata repository into a secret manager.

When the application or a database account is granted permission to read metadata, the decrypted data can still be accessed. If a secret has been stored as a JobParameter, metadata query systems, operational support tools, or exports can read that value depending on permissions.

You should combine:

- Do not store secret values in metadata.
- Grant database permissions by role and environment.
- Encrypt the application's connection to the database.
- Encrypt storage and backups.
- Restrict query permission on the metadata tables.
- Have a retention and cleanup policy for the JobRepository.
- Manage encryption keys separately from the encrypted data.

If the organization requires encryption of specific metadata fields, you need to design and test the corresponding protection mechanism according to the Spring Batch version and repository in use. Do not assume Spring Batch automatically encrypts or masks every sensitive JobParameter.

## 11. If a secret was ever written to metadata

If a previous application version passed a password or token directly in JobParameters or ExecutionContext, simply changing the code to stop passing the secret will not delete the values already stored.

You need to handle the already-existing values too:

1. Identify the type of secret and the Jobs/JobExecutions that may have stored it.
2. Rotate or revoke the secret if it may have been exposed to unauthorized people.
3. Check the scope of logs, exports, backups, and monitoring systems that may hold copies.
4. Apply a metadata retention and cleanup policy approved by the organization.
5. Handle backups according to the system's storage and expiry process.
6. Confirm the new code stores only references and does not log secrets.

Do not arbitrarily delete metadata rows of a running Job or one that needs restart. Improperly deleting metadata can lose the ability to restart, break foreign key relationships, or leave the execution history inconsistent. Use an official cleanup process and comply with audit/retention requirements.

## 12. Checking the design before putting a Job into operation

When integrating secrets into a Spring Batch Job, confirm:

| Item | What to confirm |
|---|---|
| JobParameters | Contain only business data and non-sensitive secret references |
| Identifying flag | Used to identify the JobInstance, not used as a security mechanism |
| ExecutionContext | Does not contain passwords, tokens, private keys, or credentials |
| SecretProvider | Retrieves secrets with a workload identity and least privilege |
| Step scope | The secret is only retrieved when the Step needs to execute |
| Logs and exceptions | Do not write secret values or dump all parameters |
| Restart | Clearly decide whether to use the current alias or a fixed secret version |
| Rotation | There is a process to change secrets without breaking running work |
| Database metadata | Has appropriate permissions, connection encryption, backup, and retention |
| Legacy metadata | There is a plan to handle it if secrets were stored previously |

A useful way to check is to run the Job in a test environment with a fake secret, then query the metadata repository and logs to confirm that only the reference appears. Do not use a production secret as test data. You should also check that a restart still obtains the secret under the chosen policy and that the workload account cannot read secrets outside its granted scope.

## 13. Recommended deployment model

A clear model can be organized as follows:

~~~text
JobLauncher
    |
    | JobParameters:
    |   businessDate
    |   sourceFileId
    |   credentialRef
    v
JobRepository
    |
    | Stores parameters and execution metadata
    | Does not store the secret value
    v
StepExecution
    |
    | Receives credentialRef
    v
SecretProvider
    |
    | Uses workload identity
    v
Secret Manager
    |
    | Returns the secret for the necessary operation
    v
External API
~~~

JobParameters identify the work batch and the configuration reference. The JobRepository stores metadata for identification, tracking, and restart. The SecretProvider is responsible for retrieving secrets with the workload's permissions. The Step uses the secret within the shortest possible scope and does not write it back to ExecutionContext, logs, or exceptions.

This design preserves Spring Batch's restart capability without turning metadata into a place to store credentials. When a secret needs to change, the operations team manages its lifecycle in the secret manager; when a Job needs to be restarted, the framework still uses JobParameters and non-sensitive checkpoints to identify the right work.

