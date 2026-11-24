# Do Not Store Arbitrary Sensitive Data

ExecutionContext is where Spring Batch stores the state needed to continue a job or step after an interruption. It is very useful for checkpoints, such as the position a reader has read up to, the last processed key, or the running batch code. However, because the context is persisted by JobRepository alongside batch metadata, any value placed in it can persist for a long time in databases, backups, data replicas, and operational tools.

Therefore, **do not use ExecutionContext as a secret vault, an arbitrary cache, or a place to store all input data**. Do not store passwords, access tokens, private keys, session cookies, or sensitive payloads without an explicit requirement and clearly designed protective measures. Store small checkpoints needed for restart; for sensitive data, store a controlled reference and fetch data from a protected source when needed.

This article explains what data is suitable for the context, what data should not be stored, why serialization does not equal encryption, where metadata can be exposed, and safe implementation patterns for production batch jobs.

## 1. What Is ExecutionContext Used For?

ExecutionContext is a key/value area that Spring Batch uses to hold execution state. It helps the framework restore progress after restart, while allowing batch components to share a limited amount of scoped information.

Spring Batch has two main context scopes:

| Context | Scope | Typical usage |
|---|---|---|
| Job ExecutionContext | Belongs to one JobExecution, can be shared between steps in that job | Batch code, small coordination info needed for subsequent steps |
| Step ExecutionContext | Belongs to one StepExecution | Reader checkpoint, offset, last read key |

For example, a reader reading by ascending key can store the last ID:

```java
executionContext.putLong("lastProcessedId", lastProcessedId);
```

On restart, the reader retrieves this value to continue from the appropriate position. This is small control state, not the full business data of the record.

### Where Is ExecutionContext Stored?

With JDBC JobRepository, Spring Batch stores contexts in the metadata database, typically in the tables:

- BATCH_JOB_EXECUTION_CONTEXT: context at the job execution level.
- BATCH_STEP_EXECUTION_CONTEXT: context at the step execution level.

The JDBC schema usually has columns storing a summary and serialized content, such as SHORT_CONTEXT and SERIALIZED_CONTEXT; column names and data types depend on the Spring Batch version and database.

This means the context can be read by people or applications with access to the metadata database. It can also be backed up, replicated, exported, or displayed in administration tools if those tools expose metadata.

### put() Is Not a Private Temporary Storage Area

Calling putString, putLong, or put modifies the execution's in-memory context. Spring Batch persists the context according to the job or step lifecycle and transaction/checkpoint boundaries. For steps using ItemStream, the update(ExecutionContext) method is called to write checkpoints at appropriate boundaries, usually tied to chunk commits.

Do not assume every call to put() writes immediately to the database, and do not assume the data stays only in memory. When the framework persists the context, the data becomes part of the metadata that may be retained for restart and inspection.

## 2. What Data Is Suitable to Store?

Store only small, low-sensitivity data that is genuinely needed to restore progress or pass state between steps.

Typically suitable examples:

- Line number or offset read so far.
- Ascending ID of the last processed record.
- Count of validated items or a checkpoint counter.
- Internal batch code carrying no secret information.
- Immutable file/object ID and checksum to identify the exact source.
- Data format version or schema code needed to resume.
- A small control flag with clear meaning in the flow.

Example:

```java
executionContext.putLong("lastInvoiceId", 845_200L);
executionContext.putLong("recordsValidated", 12_500L);
executionContext.putString("inputObjectId", "object-7f31a2");
executionContext.putString("inputSha256", expectedChecksum);
```

These values describe progress or reference the source data. They do not contain confidential invoice contents, credentials, or the entire file.

### Criteria for Choosing a Value to Store

Before adding a new key, ask:

1. If the process stops right now, does restart truly need this value?
2. Can the value be recomputed from a trusted source?
3. Is the value small and stable across deployments?
4. Does the value contain secrets, personal data, or sensitive business payloads?
5. Who can read job metadata, backups, and logs?
6. How long does the value need to live, and when can it be cleaned up?

If a value is not needed for restart or coordination, do not put it into the context simply because the API allows it.

## 3. Do Not Store Secrets Directly in ExecutionContext

The following types of data should not be written directly to the context:

- Database passwords, service account passwords.
- API keys, bearer tokens, OAuth access tokens, or refresh tokens.
- Private keys, certificates with private keys, signing secrets.
- Session cookies, temporary credentials, or signed URLs granting access.
- Connection strings containing username/password.
- Sensitive payment information such as card data requiring special protection.
- Payloads containing personal or customer data beyond what is needed for checkpoints.

Unsafe example:

```java
ExecutionContext context = stepExecution.getExecutionContext();

context.putString("dbPassword", databasePassword);
context.putString("partnerAccessToken", accessToken);
context.putString("privateKey", privateKeyPem);
context.putString("customerEmail", customerEmail);
```

The values above may be serialized into the metadata database. They may persist after the job finishes and be kept in backups or staging/analytics environments. Anyone with read access to batch tables can view the data if the serializer does not encrypt at the application layer.

Do not put secrets into JobParameters as an alternative. Job parameters are also stored in metadata, usually in BATCH_JOB_EXECUTION_PARAMS, and may appear in launch logs, command lines, or operational tools. Marking a parameter as non-identifying does not make it secret.

## 4. Serialization Is Not Encryption

Spring Batch needs to convert ExecutionContext into a form storable in the repository. The serializer may turn objects into strings or byte form to write to the database. This is **serialization**, not automatic security encryption.

For example, a value may be represented as text or Base64. Base64 is merely encoding; anyone with the data can decode it. Similarly, the fact that data resides in the SERIALIZED_CONTEXT column does not mean database readers cannot recover the content.

Distinguish:

| Mechanism | Purpose | Protects secrets from data readers? |
|---|---|---|
| Serialization | Converts objects into storage/transport form | No |
| Base64 or encoding | Represents data in another format | No |
| Database encryption at rest | Protects storage files or volumes while on disk | Limited; does not hide data from applications or users with query access |
| TLS in transit | Protects data over the network | Does not protect data once stored |
| Application-level encryption | Encrypts values before saving | Yes, if keys are managed separately and properly |

Do not infer confidentiality from the serializer name or database column name. Identify the configured serializer, where the data is stored, and who has read permissions.

### Why Is Database Encryption Still Not Enough for Every Case?

Encryption at rest protects data when storage is accessed directly or hardware is stolen, depending on the deployment model. However, authorized applications and database accounts can still read the decrypted data. Backups, replicas, exports, or dumps also need separate protection.

If a secret does not need to be in metadata, the best approach is not to store it there. Encryption does not turn storing arbitrary secrets into a good design.

## 5. Safe Pattern: Store Secret Reference, Fetch Secret at Runtime

Instead of storing the actual token, store a non-sensitive reference name or ID of the secret in a secret management system.

Example where the context only holds a reference:

```java
ExecutionContext context = stepExecution.getExecutionContext();
context.putString("credentialRef", "batch/partner-api");
```

When an API call is needed, the service fetches the secret from the secret manager:

```java
public class PartnerApiClient {

    private final SecretProvider secretProvider;
    private final HttpClient httpClient;

    public PartnerApiClient(
            SecretProvider secretProvider,
            HttpClient httpClient) {
        this.secretProvider = secretProvider;
        this.httpClient = httpClient;
    }

    public PartnerResponse send(PartnerRequest request) {
        String token = secretProvider.getSecret("batch/partner-api");

        return httpClient.post(
                "/invoices",
                request,
                token);
    }
}
```

SecretProvider is an application abstraction; the implementation can read from the platform's secret manager. The token is fetched at the time of use and is not written to the context or logs.

References also need review:

- Use names/IDs that do not contain credentials or tokens.
- Restrict context read access if secret names reveal sensitive systems or tenants.
- Do not store presigned URLs or URLs with embedded credentials; those can act as bearer secrets.
- Control who is authorized to resolve a reference into an actual secret.

### Secret rotation and restart

The secret manager may return a new value after a credential is rotated. This is usually desirable: the restart uses the current credential. If a business transaction requires tying to a specific credential version, store only the secret version/reference per approved policy; still do not store secret material in the context.

Do not use token values as identifying JobParameters. Tokens change on rotation and are not the identity of a business batch.

## 6. Safe Pattern: Store ID and Checksum Instead of Payload

A job may need to read large files or payloads. There is no need to put the entire content into ExecutionContext. Store the data in an appropriate location and keep only a stable reference:

```java
ExecutionContext context = stepExecution.getExecutionContext();

context.putString("sourceObjectId", sourceObjectId);
context.putString("sourceVersion", sourceVersion);
context.putString("sourceChecksum", sha256);
context.putLong("lastReadOffset", lastReadOffset);
```

On restart:

1. Fetch the object by ID/version.
2. Verify the checksum or version to confirm the content has not changed.
3. Reopen the source and resume from the checkpoint.
4. If the object has been deleted or altered, fail explicitly instead of silently reading different content.

For payloads containing sensitive data, store them in a system with appropriate encryption, access control, auditing, and retention. The context stores only an opaque ID; do not store content or signed download URLs.

### Why is a checksum useful?

Keeping the same object ID is not enough if the object can be overwritten. A checksum or immutable object version helps detect cases where a restart would read different content than the original run.

A checksum does not encrypt data and does not hide content. It only helps verify data integrity/consistency.

## 7. Store Checkpoints in the Right Scope: Job or Step

Choosing the right context scope reduces unnecessary state sharing:

- Use step context for state that only makes sense to that step's reader/writer.
- Use job context for a small value that a subsequent step needs to use.
- Do not put all data from a previous step into the job context merely to pass it to the next step.

Example of a reader implementing ItemStreamReader saving the last key:

```java
public class InvoiceIdReader implements ItemStreamReader<Invoice> {

    private static final String LAST_ID_KEY = "lastInvoiceId";

    private final InvoiceRepository repository;
    private long lastInvoiceId;

    public InvoiceIdReader(InvoiceRepository repository) {
        this.repository = repository;
    }

    @Override
    public void open(ExecutionContext context) {
        lastInvoiceId = context.getLong(LAST_ID_KEY, 0L);
    }

    @Override
    public Invoice read() {
        Invoice next = repository.findNextAfter(lastInvoiceId);
        if (next == null) {
            return null;
        }

        lastInvoiceId = next.id();
        return next;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong(LAST_ID_KEY, lastInvoiceId);
    }

    @Override
    public void close() {
        // Release resources if this reader owns any.
    }
}
```

The example assumes ID is an ascending key, the query has a stable order, and findNextAfter only reads within a finalized dataset. In real implementations, the reader must properly handle transaction boundaries, late-arriving data, and concurrency. Do not use email, tokens, or entire entities as checkpoints if only the last key is needed.

### Context between steps

If an earlier step needs to pass a batch code to a later step, you can place a small value in the job execution context per the appropriate lifecycle, such as from a listener after validating input. The later step reads back the same key. Use clearly namespaced key names, such as import.batchId, to avoid conflicts between steps.

Do not use the job context as an arbitrary shared store for multiple threads. With partitioning or multi-threaded steps, examine the context scope and synchronization mechanism of each execution.

## 8. Do Not Store Large Objects or Arbitrary DTOs

A common mistake is putting entire objects or collections into the context because it is convenient:

```java
// Do not do this
context.put("allInvoices", invoices);
context.put("customerProfile", customerProfile);
context.put("httpResponse", response);
context.put("requestBody", fullRequestBody);
```

This creates multiple risks:

- Metadata bloats and increases serialization/deserialization costs.
- Every checkpoint may have to persist large amounts of data.
- Objects whose structure changes across application versions may be incompatible on restart.
- DTOs may contain personal info, secrets, or unnecessary business data.
- Context becomes hard to inspect and hard to clean up under data policies.

Store payloads in a controlled staging table or object storage, then store only the needed ID, version, checksum, and checkpoint in the context.

### Keeping Context Stable Across Deployments

Executions may be restarted by a new application version. If the context contains arbitrary Java objects, changes to classes, packages, data types, or serializers may prevent old data from deserializing.

Primitives, string IDs, versions, and offsets are usually easier to keep compatible. If forced to store complex structures, version the context schema, define migrations, and test restarts from metadata of the previous version.

## 9. JobParameters Are Also Metadata That Must Be Protected

Some applications avoid ExecutionContext but put secrets into JobParameters instead. This is not a safe alternative.

Job parameters are saved alongside the job execution so Spring Batch can identify and describe the run. Both identifying and non-identifying parameters are metadata.

Unsafe example:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("username", username, false)
        .addString("password", password, false)
        .addString("accessToken", token, false)
        .toJobParameters();
```

Non-identifying parameters are still persisted. The identifying flag only controls JobInstance creation; it does not control access permissions or encryption.

More suitable example:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", businessDate.toString(), true)
        .addString("inputObjectId", objectId, true)
        .addString("requestId", requestId, false)
        .toJobParameters();
```

Secrets are resolved from the secret manager using configuration or protected references at runtime. Do not pass secrets via command line if there is a risk of exposure in process listings, shell history, or scheduler logs.

## 10. Other Places Where Data Can Be Exposed

It is not only the two execution context tables that need protection. Sensitive values can accidentally appear in many places:

| Location | How data can appear |
|---|---|
| BATCH_JOB_EXECUTION_CONTEXT | Serialized job context |
| BATCH_STEP_EXECUTION_CONTEXT | Step checkpoints and data stored in context |
| BATCH_JOB_EXECUTION_PARAMS | Job parameters, including non-identifying ones |
| BATCH_JOB_EXECUTION.EXIT_MESSAGE | Exception messages or error content generated by the application |
| Application log | Dumps of context, parameters, request/response, or stack traces containing values |
| Scheduler/command line | Launch arguments recorded in logs or process metadata |
| APM/tracing | Captured HTTP headers, query parameters, or payloads |
| Database backup/replica/export | Copies of the metadata database |
| Dashboard/admin tool | Screens displaying parameters or execution contexts |

Example showing exception messages should not contain tokens:

```java
// Do not do this
throw new IllegalStateException(
        "Partner request failed with token: " + accessToken);

// Do this
throw new IllegalStateException(
        "Partner request failed; correlationId=" + correlationId);
```

Log correlation IDs, job execution IDs, batch IDs, and error codes. Avoid logging credentials, raw payloads, or entire contexts.

## 11. Protecting the Metadata Database and Operational Tools

Even when the context contains only minimal data, the metadata repository still needs protection:

- Grant read/write permissions following least privilege for applications and operators.
- Separate application accounts from dashboard/reporting accounts if needed.
- Enable TLS for database connections.
- Encrypt database volumes and backups according to platform policy.
- Restrict access to dumps, replicas, and non-production environments.
- Do not let dashboards display full serialized contexts by default.
- Write audit logs for reading/exporting sensitive metadata.
- Maintain retention policies for job executions, contexts, and backups.

If a support team only needs to know which ID a job has processed up to, provide an API or screen that displays only selected checkpoints. Do not grant query access to the entire context database just to view a single number.

### Application-layer encryption when strictly mandatory

If there is a valid requirement to store a sensitive value in metadata, perform a dedicated security review. One approach is encrypting the value before placing it in the context using envelope encryption:

1. The application requests KMS to generate or use a data encryption key.
2. The value is encrypted before being saved.
3. The context holds only ciphertext, key version, and minimal metadata.
4. Decryption keys are managed outside the metadata database.
5. Decrypt permissions are restricted to necessary service accounts.
6. Processes exist for rotation, revocation, and handling old backups.

Do not invent custom encryption algorithms or hard-code encryption keys in source code, application properties, or the same database as the ciphertext. Whenever possible, still store a reference instead of secret material.

## 12. Retention and Cleanup of ExecutionContext

Contexts can live longer than the job run time because they are tied to execution metadata and support restart/investigation. Define retention periods:

- Retain contexts of running executions or ones that still need restart.
- Retain history per audit and operational requirements.
- Delete old metadata using a tested cleanup procedure that understands table relationships.
- Synchronize retention across metadata database, backups, replicas, logs, and object storage.
- Define how to handle data when jobs complete and the restart window expires.

Do not manually delete a context row currently used by an execution to "erase a secret" without assessing impact. Deleting metadata out of order can break restarts or referential integrity. If a secret was saved by mistake, first revoke/rotate the secret, then follow data handling procedures per policy while preserving necessary audit trails.

## 13. What to Do If a Secret Was Accidentally Stored in Context?

Treat that secret as potentially exposed to every principal with permission to read the corresponding metadata, logs, backups, or admin tools.

The response process should include:

1. **Revoke or rotate the secret** at the issuing system as soon as possible.
2. **Determine scope**: which job/step executions contain the value, when it was saved, and affected databases, replicas, backups, logs, and dashboards.
3. **Audit access**: inspect audit logs and metadata access permissions during the relevant timeframe.
4. **Prevent recurrence**: fix code to fetch secrets via secret manager and avoid writing values to context/parameters/logs.
5. **Handle stored data** following retention, incident response, and audit requirements; do not arbitrarily delete metadata needed for restart.
6. **Check copies**: determine how to handle backups, exports, and non-production environments per organizational policy.

Do not just remove the key from the current context and consider the incident over. Old values may still exist in historical executions, backups, logs, or database replicas. Rotating/revoking the secret is the critical step because deleting a single record does not guarantee all copies are gone.

## 14. Combined Example: Safe Reader Checkpoint and Separately Fetched Secret

A step can store a checkpoint by ID, while the API client fetches credentials from a secret provider:

```java
public class PartnerInvoiceReader implements ItemStreamReader<Invoice> {

    private static final String LAST_ID = "partner.lastInvoiceId";

    private final InvoiceRepository repository;
    private long lastInvoiceId;

    public PartnerInvoiceReader(InvoiceRepository repository) {
        this.repository = repository;
    }

    @Override
    public void open(ExecutionContext context) {
        lastInvoiceId = context.getLong(LAST_ID, 0L);
    }

    @Override
    public Invoice read() {
        Invoice invoice = repository.findNextAfter(lastInvoiceId);
        if (invoice == null) {
            return null;
        }
        lastInvoiceId = invoice.id();
        return invoice;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong(LAST_ID, lastInvoiceId);
    }

    @Override
    public void close() {
    }
}
```

The API client does not read the token from the context:

```java
public class PartnerClient {

    private final SecretProvider secretProvider;
    private final HttpClient httpClient;

    public PartnerClient(
            SecretProvider secretProvider,
            HttpClient httpClient) {
        this.secretProvider = secretProvider;
        this.httpClient = httpClient;
    }

    public void publish(Invoice invoice) {
        String token = secretProvider.getSecret("batch/partner-api");
        httpClient.post("/invoices", invoice, token);
    }
}
```

The context holds only partner.lastInvoiceId. The secret is resolved at runtime from a source with separate access control. If the job restarts, the reader restores its checkpoint and the client fetches the current credential per the rotation policy.

In a real system, ensure the reader query has a stable order, the input is finalized properly, and the writer/API has an idempotency key to handle re-sent requests safely.

## 15. Checklist Before Adding a Key to ExecutionContext

Before calling put, confirm:

- The value is genuinely needed for checkpointing, restart, or coordination.
- The value is small, with a stable data type and key name.
- It does not contain passwords, tokens, private keys, cookies, or signed URLs.
- It does not contain entire entities, large collections, or request/response payloads.
- If sensitive data is involved, the context holds only an evaluated reference/ID.
- Secrets are fetched from a secret manager at runtime and are not logged.
- Job parameters also do not contain credentials.
- Job context and step context are used in the right scope.
- Serializers and context schemas remain compatible across deployments.
- Metadata database, backups, replicas, dashboards, and logs have appropriate access/retention controls.
- A rotate/revoke and incident response procedure exists if sensitive data is saved by mistake.

## 16. Practical Conclusion

ExecutionContext is metadata for progress recovery, not a secret vault. Store small checkpoints such as offsets, last IDs, batch IDs, or object references. Do not store passwords, access tokens, private keys, session cookies, or arbitrary sensitive payloads. Serialization only converts data into a storable form; it does not automatically encrypt or protect data from anyone with repository read access.

For secrets, use a secret manager and resolve values only at runtime. For large or sensitive payloads, store them in a protected data system and keep the ID/version/checksum in the context. Protect job parameters, exit messages, logs, backups, and dashboards as well because they can also expose metadata.

A good context contains only enough information for the job to resume at the exact position. It does not contain secrets or copies of data that the application can retrieve from a securely managed source.
