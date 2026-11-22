# Creating checkpoints with synthetic data and restricted credentials

A CRaC (Coordinated Restore at Checkpoint) checkpoint image saves the state of a running Java process. The image can contain objects on the heap, loaded caches, request data, decrypted tokens, runtime configuration, and native memory regions supported by the checkpoint engine. Therefore, creating a checkpoint also creates a copy of the data and security state inside the application at that point in time.

If the application is warmed up with real customer data or uses credentials with production permissions, that data and those credentials may reside in the checkpoint image. Anyone with read access to the image can obtain sensitive information or authentication state that the application held in memory. Even when the JAR and container image do not contain secrets, the checkpoint image can still contain secrets that were loaded and decrypted at runtime.

One way to reduce risk is to create the checkpoint in an isolated environment using **synthetic data** and **restricted credentials**. The application can still initialize, warm up, and exercise processing paths without needing exposure to production data or overly broad credentials.

This article presents how to design data and identities for the checkpoint creation process, manage secrets before and after checkpoint, protect artifacts, and verify that the image does not carry unnecessary access permissions.

## 1. Why can data and credentials reside in a checkpoint?

JARs and container images primarily package the program and runtime environment. A checkpoint image, on the other hand, saves the state of the process after the program has executed partially.

For example, before checkpoint, the application may have:

- Read configuration from a secret manager.
- Created a database connection pool with a decrypted password.
- Loaded an access token into a client.
- Read customer records into a cache.
- Created sessions and kept user information in objects.
- Loaded a private key or certificate into a TLS context.
- Read messages containing personal data.
- Created native buffers containing decrypted payloads.

These values may still be referenced on the heap or in native memory at checkpoint time. The image can therefore preserve those values alongside the process state.

A simple example:

~~~text
Application startup
  -> Read secret from secret manager
  -> Authenticate to production database
  -> Load customer records into cache
  -> Warm up services
  -> Create checkpoint
       |
       +-- Heap may contain secret, token and customer data
       +-- Native memory may contain decrypted buffers
       +-- Runtime may hold client and TLS state
~~~

After restore, the objects can reappear on the heap. Restoring the process does not cause secrets to automatically expire, data to automatically become anonymized, or access permissions to automatically be revoked.

### 1.1 A checkpoint image is a sensitive copy of runtime state

Protection levels for a checkpoint image need to be applied based on the data that may reside in memory, not just based on the contents of the JAR or container image.

An image may contain:

- Cached PII or business data.
- Access tokens, refresh tokens, or session identifiers.
- Decrypted passwords, API keys, or secrets.
- Private keys or material loaded by a TLS provider.
- Cookies, authorization headers, or request bodies.
- Temporary data in buffers and uncollected objects.
- Internal information such as hostnames, endpoints, tenant IDs, and topology.

Do not assume that only objects actively serialized by the application appear in the image. The checkpoint engine handles process state at a lower level than application serialization.

## 2. Defining the goal of the checkpoint

Before preparing data and credentials, determine what the image will be used for.

Common goals:

- Testing whether the application can checkpoint and restore.
- Creating a warmed-up image for fast startup of new instances.
- Testing Resource callbacks and reconnection procedures.
- Measuring restore performance and readiness time.
- Creating artifacts used in CI or staging.
- Preparing images for production deployment.

Each goal requires different levels of data and permissions. A lifecycle test typically only needs synthetic data and sandbox credentials. An image used for production scaling may need production-compatible configuration, yet should still acquire production secrets after restore using the instance's identity instead of packaging long-lived credentials into the image.

Distinguish between:

| Goal | Suitable data | Suitable credentials |
|---|---|---|
| Testing CRaC API and callbacks | Synthetic fixtures, small dataset | No credentials needed or sandbox credentials |
| Testing database integration | Separate database with synthetic schema and data | Database user with permissions only on the test database |
| Testing OAuth/OIDC | Test tenant and test users | Sandbox client/identity, minimal scope |
| Warm-up before image creation | Synthesized representative data | Short-lived credentials, no production permissions |
| Image restored in production | Non-sensitive cache or rebuildable cache | Acquire runtime credentials after restore via workload identity |
| Testing secret rotation | Synthetic secrets with controlled version and TTL | Revocable test credentials |

Production data is not needed merely to build a workload of production-like size. Synthetic data can be generated with equivalent distribution, cardinality, and size without copying real identifying information.

## 3. Using synthetic data instead of production data

Synthetic data is data intentionally generated to simulate the structure and characteristics of real data. It is not a renamed copy of a customer dataset.

For example, instead of copying customer records and replacing names and emails, generate new data:

~~~json
{
  "customerId": "test-customer-000104",
  "name": "Nguyen Example",
  "email": "customer-104@example.invalid",
  "segment": "STANDARD",
  "createdAt": "2026-10-01T08:00:00Z"
}
~~~

The `.invalid` domain is reserved for testing purposes and does not represent a deliverable email address. Example values should follow the specific conventions of the test system.

### 3.1 Synthetic data differs from masking and anonymization

| Approach | How it is created | Remaining risk |
|---|---|---|
| Synthetic data | Generate new records following schema and simulation rules | Lower if no values or secrets are copied from real sources |
| Masking | Replace certain fields such as name, email, phone number | Identifying data may remain through other fields or multi-table joins |
| Pseudonymization | Replace direct identifiers with pseudonyms | Re-identification is possible if mapping tables or auxiliary data remain |
| Anonymization | Process data to reduce the ability to identify individuals | Quality depends on techniques and joinability with external data |

Masking does not automatically turn production data into harmless data. A dataset with replaced names that still preserves exact birth dates, addresses, rare transaction histories, or relationships across tables may still identify an individual.

If the goal is creating a test checkpoint, prefer generating new data. If using production-derived data is unavoidable, a dedicated privacy review process, re-identification risk check, and restricted access controls are required. Do not treat replacing names or hashing emails as complete anonymization.

### 3.2 Keeping necessary structure and distribution

Synthetic data still needs to be representative enough for meaningful warm-up. Identify attributes important to the workload:

- Record count and cardinality.
- Payload size distribution.
- Ratios of statuses and business types.
- Foreign key relationships.
- Missing or null data.
- Long strings, Unicode characters, and boundary data.
- Past and future timestamps.
- Records with completed, failed, or pending states.
- Cases that trigger different processing branches.

Real values do not need to be copied to preserve distribution. For example, 100,000 synthetic customers can be generated with segment ratios matching approved aggregate statistics, while using completely new IDs and attributes.

### 3.3 Using consistent data across tables

If the application needs customer, order, and payment data, create fixtures with consistent relationships:

~~~sql
INSERT INTO customer(customer_id, display_name)
VALUES
    ('test-customer-001', 'Customer Example 001'),
    ('test-customer-002', 'Customer Example 002');

INSERT INTO orders(order_id, customer_id, status)
VALUES
    ('test-order-001', 'test-customer-001', 'PENDING'),
    ('test-order-002', 'test-customer-002', 'PAID');
~~~

This is an illustrative example only. Use a separate namespace or database so fixtures cannot write into production.

If using a generator, generate IDs with clear prefixes such as `test-`, `synthetic-`, or `fixture-`. However, prefixes do not replace database and network isolation. A misconfiguration can still send fixtures to a real system.

### 3.4 Synthetic data must avoid real side effects

Fixtures should not trigger:

- Emails to real customers.
- Real SMS messages or phone calls.
- Real payments or refunds.
- Webhooks to real partners.
- Creation of production accounts or API keys.
- Messages to production topics.
- Transactions or reports treated as real business metrics.

Use fake SMTP, mock payment providers, sandbox endpoints, separate message brokers, and network policies blocking egress to production. If protocol testing is required, use the provider's official sandbox.

## 4. Isolating the checkpoint creation environment

Synthetic data is only meaningful if the application cannot accidentally access production. The checkpoint creation environment should have clear boundaries for network, identity, storage, and permissions.

### 4.1 Separating environments

Use a dedicated environment for the checkpoint creation process, for example:

~~~text
checkpoint-build
  |
  +-- synthetic database
  +-- test message broker
  +-- sandbox identity provider
  +-- fake email/payment endpoints
  +-- test object storage
  +-- restricted secret store
~~~

Do not share production databases, brokers, or buckets and rely solely on schema names or prefixes to distinguish them. Separate accounts, projects, subscriptions, or network boundaries when the platform supports it.

### 4.2 Network egress policy

The checkpoint creation container should only connect to listed dependencies. Network policies, firewalls, or egress gateways can be used to:

- Block production IP ranges and endpoints.
- Allow only sandbox services.
- Block unnecessary metadata endpoints.
- Block internet access depending on test goals.
- Log denied connections.

An explicit endpoint allowlist is safer than merely hoping the application will not call the wrong URL.

### 4.3 Separating storage

Use dedicated volumes and buckets for:

- Fixture data.
- Checkpoint job logs.
- Temporary files and mapping files.
- Checkpoint artifacts.
- Test reports.

Do not mount production volumes into the checkpoint creation container without an approved requirement. A read-only mount does not turn production data into synthetic data; it can still be pulled into the heap or checkpoint image if the application reads it.

### 4.4 Explicit environment configuration

Include environment identity in configuration and verify it before warm-up:

~~~yaml
environment:
  name: checkpoint-build
  dataMode: synthetic
  allowProductionEndpoints: false

dependencies:
  database: checkpoint-test-db
  identityProvider: sandbox
  messageBroker: checkpoint-test-broker

checkpoint:
  enabled: true
  artifactClass: restricted-test
~~~

This is an illustrative configuration structure defined by the application. Validate configuration before opening connections. If the environment is wrong or an endpoint is not on the allowlist, abort the checkpoint creation process.

Do not put real secrets in YAML, Dockerfiles, build arguments, or source repositories.

## 5. Designing credentials with least privilege

Credentials used during checkpoint creation should only have the permissions needed for startup and warm-up steps.

Apply the least privilege principle:

- Access only a single test database or test schema.
- Read only tables needed for warm-up if writing is unnecessary.
- Write only into the fixture namespace.
- Publish only to test topics.
- Call only sandbox APIs.
- No account or subscription administration permissions.
- No permission to read production secrets.
- No permission to create new credentials outside test scope.
- Do not use the same credential for CI, checkpoint jobs, and production runtime.

### 5.1 Separating identities by role

Distinguish at least three identities:

| Identity | Responsibility | Required permissions |
|---|---|---|
| Build identity | Build JAR/container and publish artifacts | Read build dependencies, write to designated artifact registry |
| Checkpoint identity | Start application, access fixtures, and warm up | Access only sandbox dependencies and synthetic data |
| Runtime identity | Serve workloads after restore | Business permissions necessary for the specific service/tenant/instance |

Do not use the build identity as the runtime identity. Do not grant production permissions to the checkpoint identity merely for warm-up to succeed.

If a checkpoint image is created in a test environment and restored in production, the application must obtain a new runtime identity via the instance's workload identity after restore. Do not inherit test credentials in the image to call production services.

### 5.2 Scope and audience

With OAuth or token-based authentication, restrict:

- Scopes sufficient only for the APIs that must be called.
- Audience matching the exact resource server.
- Tenant or project belonging only to the sandbox.
- Short token expiration.
- Permissions excluding admin or wildcards unless needed.
- Tokens unusable in production.

A token with narrow scopes yet a production audience can still pose risks. Verify issuer, audience, scope, tenant, and resource server.

### 5.3 Short-lived credentials

Prefer credentials with a short TTL that can be revoked. Do not create static passwords shared across multiple checkpoint runs.

Checkpoint credentials should have:

- An expiration aligned with image creation and testing duration.
- Permissions restricted by resource.
- A clear owner.
- A revocation procedure after completion.
- Audit logs of issuance and usage.
- No reuse as production credentials.

A short TTL reduces the exposure window, but does not automatically remove the secret from the image. If a token remains on the heap after expiration, it is still sensitive data that needs protection.

### 5.4 Do not use production credentials just for warm-up

Warm-up often needs to execute representative queries, connections, and operations. These operations can be executed using sandbox credentials and synthetic data.

If latency close to production needs to be measured, use a staging environment with equivalent configuration rather than production permissions. If a step can only be executed in production, separate that step from checkpoint creation and execute it after restore using the runtime identity.

## 6. Keeping long-lived secrets out of checkpoints

The best principle is not to load long-lived production secrets into the process before checkpointing.

Instead of:

~~~text
Start application
  -> Load production password
  -> Create production connection pool
  -> Warm up
  -> Checkpoint
~~~

Organize it as:

~~~text
Create checkpoint in isolated environment
  -> Use synthetic data
  -> Use sandbox credential with limited scope
  -> Warm up safe code paths
  -> Close sandbox clients
  -> Remove checkpoint-only credential references
  -> Create restricted checkpoint artifact

Restore in target environment
  -> Obtain instance-specific runtime identity
  -> Fetch current secrets
  -> Create production clients
  -> Reconcile external state
  -> Mark ready
~~~

This reduces the risk of the image containing production credentials and avoids accidentally calling test endpoints after restore.

### 6.1 Obtaining secrets after restore

If the workload runs on a platform with workload identity, the instance can authenticate with the secret manager after restore and fetch current secrets.

Reference flow:

1. Container/instance is granted a dedicated identity by the platform.
2. Application authenticates using workload identity.
3. Secret manager verifies identity and policy.
4. Application retrieves the specific or current secret version.
5. Clients are recreated using the new credentials.
6. Readiness is enabled only after verification succeeds.

The exact secret manager, workload identity, and API depend on the cloud/platform. Do not hard-code credentials into the checkpoint to replace the platform's identity mechanism.

### 6.2 Do not fetch new secrets and write them back into an old checkpoint

A checkpoint image is an immutable artifact for a given creation run. If you restore and swap secrets on the heap, that change belongs to the restored process; it does not update the original image file.

If creating a new checkpoint from a restored process, re-evaluate all data and credentials on the heap before saving the next image. Do not turn an image that originally held only test credentials into a new image with production credentials without proper security procedures and artifact classification.

## 7. Handling credentials already in memory

Sometimes the application must authenticate with a sandbox to warm up. In that case, minimize credential data remaining in the image.

### 7.1 Stopping refresh tasks and clients

Before checkpoint:

- Stop background token refresh.
- Stop accepting new requests.
- Drain requests currently using credentials.
- Close sandbox connection pools and clients.
- Cancel schedulers or callbacks that could continue using tokens.
- Clear credential caches if not needed for restore.
- Verify no threads are still using secrets.

Closing clients does not guarantee that all copies of credentials on the heap or in native memory have been erased. It is only one part of lifecycle cleanup.

### 7.2 Mutable buffers and best-effort zeroization

If the application manages secrets directly in a byte array, memory can be overwritten before dropping the reference:

~~~java
import java.util.Arrays;

public final class SecretBytes implements AutoCloseable {

    private byte[] value;

    public SecretBytes(byte[] value) {
        this.value = value.clone();
    }

    public synchronized byte[] copy() {
        if (value == null) {
            throw new IllegalStateException("Secret is closed");
        }
        return value.clone();
    }

    @Override
    public synchronized void close() {
        if (value != null) {
            Arrays.fill(value, (byte) 0);
            value = null;
        }
    }
}
~~~

This is only best-effort zeroization for the buffer owned by the class. It does not erase previously created copies, library buffers, native memory, CPU registers, swap, or memory pages copied by the runtime/checkpoint engine. Absolute erasure cannot be guaranteed solely with Arrays.fill().

### 7.3 Strings cannot have their contents erased in place

Java Strings are immutable. Once a secret is converted to a String, the application cannot overwrite the String object's contents using standard Java APIs.

Assigning a variable to null only drops one reference. The Garbage Collector may reclaim the object later, but there is no guarantee on timing or whether the old memory region is overwritten before checkpoint.

Therefore:

- Avoid converting secrets to Strings if APIs allow char[] or byte[].
- Avoid creating multiple copies when formatting or concatenating strings.
- Do not log secrets or exception messages containing secrets.
- Do not hold tokens in static fields longer than necessary.
- Do not rely on System.gc() to erase secrets.
- Ideally, do not load sensitive credentials before checkpoint.

Even when using mutable arrays, libraries may create internal copies. Treat zeroization as a risk-reduction measure, not a reason to put production secrets into an image.

### 7.4 TLS contexts and private keys

SSLContext, KeyManager, TrustManager, or providers can hold key material in the object graph or native memory. Closing sockets does not necessarily erase all loaded key material.

If the checkpoint only needs to warm up code paths, use test certificates. Recreate TLS contexts with current certificates/secrets after restore. Do not put production private keys into images created in CI or staging.

## 8. Managing Resource callbacks for checkpoint-only credentials

A CRaC Resource can be used to stop and release resources used only during checkpoint creation, then create new runtime clients after restore.

The following example describes the structure:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class CheckpointClientResource implements Resource {

    private final CheckpointClientFactory checkpointFactory;
    private final RuntimeClientFactory runtimeFactory;

    private CheckpointClient checkpointClient;
    private RuntimeClient runtimeClient;

    public CheckpointClientResource(
            CheckpointClientFactory checkpointFactory,
            RuntimeClientFactory runtimeFactory) {
        this.checkpointFactory = checkpointFactory;
        this.runtimeFactory = runtimeFactory;

        this.checkpointClient = checkpointFactory.createSandboxClient();
        Core.getGlobalContext().register(this);
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        if (checkpointClient != null) {
            checkpointClient.stopAndDrain();
            checkpointClient.clearCredentialReferences();
            checkpointClient.close();
            checkpointClient = null;
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        runtimeClient = runtimeFactory.createForCurrentInstance();
        runtimeClient.validateConnection();
    }
}
~~~

The CheckpointClient, RuntimeClient, and factory types in the example are application abstractions, not built-in CRaC APIs. The example illustrates separating the sandbox client from the runtime client.

Key points to note:

- The checkpoint client is only permitted to access the sandbox.
- The runtime factory acquires the current instance's identity after restore.
- Do not transfer sandbox credentials to the runtime client.
- Do not open readiness just because the runtime client object has been created.
- If fetching credentials or validation fails, propagate the error or keep the application in an unready state according to the designed lifecycle.
- If beforeCheckpoint fails, CRaC may invoke restore notifications to recover resources in the original process; callbacks must handle partially closed state.

When the afterRestore callback is invoked in a new process, the runtime factory needs to obtain the identity corresponding to that instance. Do not use a static token or an identity checkpointed from the source instance.

### 8.1 Do not make unbounded network calls in callbacks

Fetching secrets or authenticating after restore can encounter timeouts. Use connect timeouts, request timeouts, and bounded retries. Do not keep callbacks waiting indefinitely.

If the framework allows asynchronous dependency recovery, keep readiness false until the runtime client is operational. Maintain clear states across RESTORING, RECONNECTING, RECONCILING, and READY.

## 9. Verifying no checkpoint credentials remain in the image

There is no single general tool that can prove every byte of a secret has vanished from a checkpoint image. Multiple controls can be combined:

- Design so production secrets are never loaded before checkpoint.
- Use short-lived, revocable sandbox credentials.
- Stop refresh tasks and close clients.
- Clear references and zeroize mutable buffers owned by the application.
- Do not log tokens, passwords, or authorization headers.
- Inspect heap dumps or object inventories in a test environment if appropriate.
- Verify configuration files, environment, and metadata contain no secrets.
- Test restore and verify that sandbox credentials have expired or been revoked.
- Verify that new runtime credentials are issued after restore.
- Protect the checkpoint artifact as sensitive data even after scrubbing.

### 9.1 Secret scanning is insufficient to prove an image is clean

Scanners can find token strings or password patterns in files, but a checkpoint image may contain compressed memory pages, binary structures, or data without easily recognizable text formats.

A scan finding no secrets does not prove there are no secrets. Prevention through identity and data isolation is more important than merely scanning artifacts after creation.

### 9.2 Testing token replay in a sandbox

You can create a test token with narrow scope and short TTL, then check:

1. The token works before checkpoint in the sandbox.
2. The token is revoked or expires according to the test plan.
3. The image is restored.
4. The application does not continue using the old token.
5. A new runtime identity is issued.
6. Sandbox requests using the new credentials succeed.
7. No production requests are generated.

Do not use production tokens to test replayability. Tests should record token references or fingerprints, without logging raw tokens.

## 10. Protecting the checkpoint artifact

Even when using synthetic data and restricted credentials, the checkpoint image still needs protection. It can contain internal structures, test data, temporary secrets, and runtime state that could be abused.

### 10.1 Least privilege access

Restrict who can:

- Create checkpoints.
- Read or download artifacts.
- Copy images to other environments.
- Restore images.
- Delete or replace artifacts.
- Read accompanying metadata and logs.

Separate container image publishing permissions from checkpoint artifact download permissions if the platform allows. Anyone with permission to read a checkpoint can observe far more runtime state than someone who can only pull a JAR.

### 10.2 Encryption at rest and in transit

Use platform-provided storage and transport encryption. Manage encryption keys separately from artifacts:

- Do not store encryption keys inside the checkpoint.
- Restrict decrypt permissions to authorized workloads or pipelines.
- Audit decrypt operations.
- Establish a key rotation procedure.
- Verify that backups and replica storage are also encrypted.

If images move between registries, object storage, and nodes, protect every leg of transfer. Checksums verify integrity but do not replace encryption or access control.

### 10.3 Integrity and provenance

Attach immutable metadata to the checkpoint:

~~~yaml
artifact:
  checkpointId: orders-test-2026-11-13-001
  applicationBuild: 2.8.1
  containerDigest: sha256:example-container-digest
  createdFrom: checkpoint-build
  dataClassification: synthetic
  credentialClass: sandbox-short-lived
  createdAt: "2026-11-13T07:00:00Z"
  checksum: sha256:example-checkpoint-digest
~~~

This is an illustrative manifest defined by the pipeline. Do not include secret values, tokens, or private keys in metadata.

Manifests or artifacts can be signed using the organization's signing mechanism to verify provenance and detect tampering. Only restore artifacts with accepted provenance.

### 10.4 Retention and deletion

Set checkpoint retention periods according to purpose:

- CI checkpoints may only exist for a short time.
- Staging checkpoints are kept according to the release window.
- Production checkpoints have retention aligned with rollback policy.
- Artifacts containing test credentials must be revoked or expire on schedule.

When deleting, account for copies in backups, replicas, registry caches, and CI workspaces. Deleting an object in the primary bucket does not guarantee all copies are gone.

### 10.5 Do not accidentally publish to public registries

A checkpoint image should not be pushed to a public registry merely because the corresponding container image is public. Verify destinations and ACLs in the pipeline. Use a dedicated registry or bucket for checkpoint artifacts.

## 11. Safe checkpoint creation pipeline in CI/CD

A pipeline can be organized as follows:

~~~mermaid
flowchart TD
    A["Build JAR and container image"] --> B["Create isolated checkpoint environment"]
    B --> C["Provision synthetic fixtures"]
    C --> D["Issue sandbox-only credentials"]
    D --> E["Start application and warm up"]
    E --> F["Verify no production route or identity"]
    F --> G["Stop traffic and drain work"]
    G --> H["Close sandbox clients and scrub owned secrets"]
    H --> I["Create checkpoint"]
    I --> J["Store encrypted restricted artifact"]
    J --> K["Revoke checkpoint credentials"]
    K --> L["Restore in isolated target"]
    L --> M["Acquire new instance identity"]
    M --> N["Validate dependencies and readiness"]
    N --> O["Publish with provenance and retention"]
~~~

The exact sequence depends on the application and engine. Some credentials may need to remain valid for the restore test step immediately after checkpoint; keep them in a sandbox with minimal permissions, then revoke according to the test plan. If the image will be retained longer than the credential TTL, do not rely on that credential upon restore.

### 11.1 Provision fixtures before starting the application

Schema and synthetic data can be created via a separate migration/fixture job. The application receives access permissions only to the test database.

This avoids the application misdetecting the environment and creating data on an unintended database.

### 11.2 Warm-up uses only safe paths

Warm-up should exercise necessary code paths without creating production side effects. Use sandbox providers for payment, email, object storage, message brokers, and identity.

If a processing path cannot be simulated safely, warm up up to the point before the external side effect call or use a mock with the same interface.

### 11.3 Create the image after stopping work

Before checkpoint:

- Stop accepting requests.
- Drain in-flight requests.
- Stop consumers and schedulers.
- Finish transactions.
- Close sandbox clients.
- Clear unnecessary temporary data.
- Verify no background tasks are still using credentials.

Do not create a checkpoint in the middle of an operation that could cause undefined side effects in external systems.

### 11.4 Test restore with a new identity

In the restore test, issue a sandbox runtime identity different from the identity that created the checkpoint. This proves the application actually acquires new credentials after restore rather than reusing credentials from the image.

Check logs of the identity provider or secret manager to confirm which identity fetched secrets and when. Do not write secret values into logs.

## 12. Using checkpoints for production without carrying production credentials in the image

A commonly used strategy is creating the image from a compatible environment without containing production credentials.

Before checkpoint:

- Use synthetic data or non-sensitive caches.
- Use a sandbox identity to warm up.
- Close sandbox clients.
- Do not load production secrets.
- Attach metadata on build and config compatibility.

After production restore:

- Platform grants an instance-specific workload identity.
- Application fetches production secrets from the secret manager.
- Recreate connection pools and network clients.
- Reconcile configuration and external state.
- Verify schema, endpoints, and permissions.
- Open readiness only after that.

If the application needs production data to serve immediately after restore, load that data after restore from an authoritative source. If pre-caching is required, consider non-sensitive data or encrypted caches with a dedicated policy; do not put customer data into images by default.

### 12.1 Separating warm-up from loading real data

Warm-up can rely on:

- Synthetic records.
- Newly generated sample requests.
- Synthetic cache keys.
- Queries with test results.
- Non-sensitive models or metadata.
- Code paths executed with mock/sandbox dependencies.

The goal of warm-up is class loading, JIT compilation, and initializing required structures. Not all real business data needs to sit on the heap to achieve that goal.

### 12.2 Production caches need a dedicated policy

If a cache containing production data is essential to reduce latency, evaluate:

- Does the data contain PII or secrets?
- Can it be rebuilt after restore?
- Does stale data cause business logic errors?
- Are there TTLs and versions?
- Who has permission to read the checkpoint artifact?
- Will the image be restored in a different environment?
- Can cached data be encrypted at the application layer?
- Can the cache be loaded after restore per tenant/instance identity?

Keep caches in the image only when benefits and risks have been identified and corresponding protection mechanisms exist.

## 13. Managing multiple instances restored from the same image

If one checkpoint is used to spawn multiple instances, every object in the image can be cloned simultaneously. This is especially dangerous for credentials or state that require uniqueness.

Risks:

- Multiple instances share a single refresh token.
- Multiple instances use an API key with concurrency limits.
- Multiple instances carry the same session or source identity.
- Multiple instances use a single client certificate.
- Multiple instances own the same lease or scheduled job.
- One instance revokes a credential, causing other instances to lose access.

### 13.1 Granting identity per instance

After restore, each instance should acquire its own identity from the platform or identity provider. Credentials should be bound to a specific workload, pod, VM, or service account.

Do not use a UUID or token generated before checkpoint as the unique identity of all replicas.

### 13.2 Do not share refresh tokens in the image

Refresh token rotation can cause the first instance using the token to succeed while subsequent instances are rejected. If the image is cloned, token state on the heap is also cloned.

Use one of these designs:

- Each instance receives its own credentials after restore.
- A single token broker manages refresh tokens.
- Credentials can be re-issued independently for each workload.
- Use concurrency control and atomic token rotation if supported by the issuer.

### 13.3 Shared resources need external coordination

A checkpoint image is not a distributed lock. Use a lease service, database lock, compare-and-set, or fencing tokens to manage ownership. Do not allow a boolean on the heap to decide which instance is allowed to execute side effects.

## 14. Testing synthetic data and restricted credentials

A safe test needs to prove both things: the data used is synthetic and the credentials have properly scoped permissions.

### 14.1 Data checks

- Fixtures have a documented source and generator.
- No real customer records.
- No emails or phone numbers capable of contacting real individuals.
- No tokens or secrets copied from production.
- Data relationships and distribution are sufficient for workload tests.
- Logs and reports contain no sensitive payloads.
- Datasets can be regenerated and deleted after tests.

If using production-derived data, provide evidence of privacy review and an approved anonymization process. Do not rely solely on field names or `test` prefixes.

### 14.2 Credential checks

- Issuer is accurately the sandbox or test identity provider.
- Audience matches the test resource.
- Smallest necessary scope.
- Credentials have a TTL.
- Credentials are revocable.
- No production permissions.
- No unnecessary admin permissions.
- Identities are distinct between checkpoint build and restored instance.
- Secrets are not printed into logs or metadata.
- Runtime identity is re-issued after restore.

### 14.3 Network and destination checks

- Production endpoints are blocked from the checkpoint environment.
- Database hostnames and accounts belong to test.
- Brokers/topics belong to test.
- Email/payment providers are fake or sandbox.
- Object storage buckets belong to test.
- Restore target only accesses dependencies on the allowlist.
- Network policy results are saved alongside the test report.

### 14.4 Checkpoint artifact checks

- Checksums are verified.
- Artifacts are stored in restricted storage.
- Encryption is enabled.
- ACLs are verified.
- Manifest contains no secrets.
- Retention is time-bounded.
- Artifacts are not published to public registries.
- Restore tests use a new identity and verify old credentials are not used.

## 15. Failure scenarios and remediation

| Scenario | Risk | Desired behavior |
|---|---|---|
| Application points to production database by mistake | Real data leaks into heap/image | Block connection via network policy and fail fast on environment mismatch |
| Checkpoint credentials have overly broad scope | Image contains excess permissions | Revoke, discard artifact, and recreate with minimal scope |
| Token remains alive after restore | Test credential continues to be used | Check expiry/revocation and disallow reuse |
| Production secret loaded before checkpoint | Secret may reside in the image | Do not publish image; handle credential incident and recreate image safely |
| Secret String cannot be zeroized | Copies may remain on the heap | Do not rely on GC; avoid loading secrets before checkpoint |
| Restoring multiple replicas with the same token | Rotation/reuse or conflict | Issue per-instance credentials |
| Secret manager unavailable after restore | Cannot create runtime client | Keep readiness false, retry with limits, and report error |
| Fixtures send real emails | Side effects to users | Fake SMTP, block egress, and use test addresses |
| Artifact downloaded without authorization | Exposure of heap data or credentials | Revoke credentials, audit, handle incident, and withdraw artifact |
| Restore uses sandbox configuration | Production instance calls test service by mistake | Reconcile environment config before readiness |

If a checkpoint image is discovered to contain production credentials or unauthorized data, treat it as an artifact security incident. Merely deleting a reference in the application does not revoke stored copies. Revoke credentials, determine the scope of artifacts and backups, restrict access, and rebuild the image from a clean environment.

## 16. Observability and auditing

Every checkpoint creation should have logs and metadata sufficient to answer:

- Which environment created the image?
- Which dataset was used and what generator version?
- Which credential class was issued?
- Which issuer and audience does the credential belong to?
- What are the TTL and revocation time?
- Which container/JDK/engine build created the image?
- Who or which pipeline created and published the image?
- Where is the artifact stored and who downloaded it?
- Did the restored instance acquire a new identity?
- Were there any requests to production endpoints during the checkpoint build?

Do not log secret values. Use non-sensitive IDs, versions, or fingerprints.

Useful metrics:

- Number of checkpoint builds rejected due to environment mismatch.
- Number of requests blocked by network policy.
- Warm-up and checkpoint duration.
- Number of sandbox credentials issued.
- Number of credentials revoked after build.
- Number of successful restores using a new identity.
- Number of reconnection or secret retrieval errors.
- Time from restore to readiness.

Audit logs need protection from modification and appropriate retention. Permissions to view audit logs also need control.

## 17. Pre-checkpoint checklist

The following list can be used in pipelines or runbooks:

### Data

- [ ] Dataset is freshly generated by an approved generator or fixture.
- [ ] No raw copies of production databases are used.
- [ ] No real PII or secrets outside approved scope.
- [ ] Fixtures have sufficient relationships and distribution for the workload.
- [ ] Email, payment, webhook, and message side effects are sandboxed.
- [ ] Logs contain no sensitive payloads.

### Credentials and identity

- [ ] Checkpoint identity is separate from build and runtime identities.
- [ ] Scope, audience, tenant, and resources are restricted.
- [ ] Credentials have a short TTL and revocation capability.
- [ ] No unnecessary production permissions.
- [ ] Production secrets are only fetched after restore if possible.
- [ ] Refresh tasks and clients are managed in the lifecycle.
- [ ] No tokens, passwords, or private keys are logged.

### Environment

- [ ] Database, broker, identity provider, and storage belong to sandbox.
- [ ] Network egress blocks production endpoints.
- [ ] Volumes and mounts contain no production data.
- [ ] Environment configuration is validated before warm-up.
- [ ] CI runners do not have permission to read production secrets.

### Artifact

- [ ] Checkpoint image is classified and tagged with metadata.
- [ ] Artifact is encrypted and stored in restricted storage.
- [ ] Checksum or signature is verified.
- [ ] Read, restore, and publish permissions are separated.
- [ ] Artifact retention and deletion are defined.
- [ ] Restore test acquires a new runtime identity.

## 18. Recommended implementation workflow

When building checkpoints for Java applications, you can follow this sequence:

**Step 1 — Define goals and scope.** Clarify whether the image is for CI, staging, or production deployment; identify data and dependencies needed for warm-up.

**Step 2 — Create an isolated environment.** Use sandbox databases, brokers, identity providers, storage, and endpoints. Block network access to production.

**Step 3 — Generate synthetic data.** Create new fixtures with representative schema, relationships, and distribution. Avoid copying raw production data or merely renaming fields on real data.

**Step 4 — Issue checkpoint credentials.** Use a dedicated identity, small scope, exact audience, short TTL, and revocable permissions.

**Step 5 — Start up and warm up.** Execute only safe processing paths with fixtures and sandbox dependencies. Monitor all network destinations.

**Step 6 — Prepare before checkpoint.** Stop accepting work, drain threads, stop refresh tasks, close clients, and clear secret buffers owned by the application.

**Step 7 — Create and protect the image.** Record metadata, checksum, encrypt, and store the artifact in restricted storage. Do not publish to public registries.

**Step 8 — Revoke test credentials.** Revoke or let credentials expire per policy; retain audit evidence without recording secrets.

**Step 9 — Restore with a new identity.** Grant a dedicated workload identity to the instance, fetch current secrets, and recreate clients. Verify old checkpoint credentials are not used.

**Step 10 — Verify readiness and side effects.** Verify dependencies, environment, data, and absence of unintended production requests.

**Step 11 — Enforce retention.** Delete test fixtures, logs, and checkpoints upon expiration; check copies and backups as well.

## References

- [CRaC — What CRaC is](https://crac.org/about/about-crac/): checkpoint/restore model and saved process state.
- [CRaC — Integrating CRaC in your Application](https://docs.azul.com/crac/usage/integrating-crac): managing Resources via beforeCheckpoint and afterRestore.
- [CRaC — Debugging](https://crac.org/reference/debugging/): investigating resource state and checkpoint/restore failures.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): secret lifecycle, access permissions, and management.
- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): protecting sensitive data at rest.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): authentication, sessions, and credentials.
- [OWASP Database Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Database_Security_Cheat_Sheet.html): database authorization and protection.
- [NIST SP 800-207 — Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final): authentication and authorization by identity, resource, and context.
- [NIST SP 800-57 Part 1](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): key material lifecycle management and protection.
- [RFC 6749 — OAuth 2.0](https://www.rfc-editor.org/rfc/rfc6749): access tokens, scopes, and token responses.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): protecting refresh tokens and reducing replay risks.
