# Loading or refreshing secrets after restore and the limitations of erasing traces on the heap

A CRaC checkpoint saves the memory state of a JVM process at a point in time. If the application is holding passwords, access tokens, API keys, loaded private keys, session credentials, or authentication data on the heap, those values may be written into the checkpoint image. When the image is stored, copied, or transferred to another environment, the secrets can travel with the image and persist longer than their intended lifecycle.

An important security strategy is to load or refresh secrets only after restore, right before the components that need them are allowed to operate. Before checkpoint, the application should stop using credentials, close or release objects holding secrets when possible, and eliminate temporary copies according to the API's capabilities. However, it cannot be guaranteed that every trace of secrets is erased from the Java heap merely by setting a variable to null or overwriting an array.

The JVM has a garbage collector that can copy objects during heap compaction, libraries can create internal copies, and some APIs represent secrets using immutable Strings. Old data can also remain in memory regions that have not yet been reused. Therefore, zeroization in Java is only a limited risk-reduction measure; it does not replace keeping secrets out of the checkpoint, protecting the image, and restricting access permissions.

This lesson focuses on three principles:

- **Do not package long-lived secrets if they can be obtained after restore.** Prefer workload identity and a secret manager to issue short-lived credentials when the instance runs.
- **Refresh in the proper lifecycle order.** Secrets must be ready before database pools, HTTP clients, brokers, or TLS components that need them reconnect.
- **Do not claim the heap has been completely scrubbed.** Clearing references and overwriting buffers only reduce the likelihood of exposure; combine this with artifact controls, encryption, rotation, and testing.

## 1. Why can secrets be stored in a checkpoint?

An application typically loads secrets at startup and retains them in the object graph for repeated use. For example:

- Database passwords in configuration or connection pools.
- Access tokens and refresh tokens in HTTP clients.
- API keys in singletons or static fields.
- Private keys or secret keys in cryptographic provider objects.
- Credentials used to connect to message brokers, caches, or cloud APIs.
- Cookies, session IDs, and authorization headers in requests or caches.
- Secrets decrypted from environment variables, file mounts, or a secret manager.

At checkpoint time, referenced objects can be saved along with the heap. If the image is moved to an environment with different access permissions, anyone able to read the image may have an opportunity to recover that sensitive data. Exactly which data gets recorded also depends on process state, the checkpoint mechanism, native memory, and how libraries manage secrets; do not assume a credential only exists in a single field.

### A common example

~~~java
public final class DatabaseConfig {
    private final String username;
    private final String password;

    public DatabaseConfig(String username, String password) {
        this.username = username;
        this.password = password;
    }
}
~~~

If this object is created before checkpoint and is still referenced by a bean or pool, password may reside in the heap image. Setting a local variable holding the password to null does not erase the field in another object. Even when the object is no longer used by the application, the old bytes may still remain in heap memory that has not been overwritten.

### Distinguishing secrets from normal configuration

Not all configuration is a secret. Database hostnames, service names, ports, or feature flags may not be sensitive, depending on the architecture. Passwords, tokens, private keys, and authentication data must be classified separately.

| Data | Example | Handling around checkpoint |
|---|---|---|
| Non-secret configuration | Service name, port, timeout | Can be retained if compatible with the restore environment |
| Long-lived secrets | Static password, API key | Avoid storing in the image; move to a secure issuance mechanism |
| Short-lived credentials | Access token, temporary DB password | Refresh after restore and bound TTL |
| Private keys | TLS or signing keys | Prefer HSM/KMS or non-exportable providers; if loaded into the JVM, minimize duration and copies |
| Session/request data | Cookie, authorization header | Do not leave in caches or buffers that may be checkpointed if unnecessary |
| Bootstrap secrets | Workload identity token or credential to access secret manager | Protect at the same sensitivity level; do not assume bootstrap secrets are unimportant |

## 2. Designing so secrets are loaded after restore

Instead of putting passwords or tokens into the image, the application can hold a provider that knows how to fetch secrets from a trusted source when needed. This source can be a secret manager, KMS, workload identity, service account, or a platform-provided credential issuance mechanism.

General flow:

~~~mermaid
flowchart TD
    A[Application is ACTIVE] --> B[Close admission and drain requests]
    B --> C[Close secret-dependent clients]
    C --> D[Release secrets to the extent possible]
    D --> E[Checkpoint]
    E --> F[Restore JVM]
    F --> G[afterRestore]
    G --> H[Authenticate current workload identity]
    H --> I[Obtain new secret or token]
    I --> J[Reinitialize database, HTTP, and broker clients]
    J --> K[Verify dependencies]
    K --> L[Open readiness]
~~~

The key point is that the secret provider and the clients using secrets also have lifecycles. If the secret manager client holds a stale socket or an expired bootstrap credential, calling the provider right after restore may fail. The identity/bootstrap path must be recovered first, and only then should application secrets be fetched.

### Workload identity instead of packaged credentials

If the platform supports workload identity, the application can prove its identity using credentials issued by the runtime or orchestrator, then receive a short-lived token. This token can be scoped:

- By service or workload.
- By audience and scope.
- By short expiration.
- By environment or namespace.
- By access permissions to specific secrets.

Do not use a single shared long-lived token for all replicas if the platform can issue distinct identities. If a token is stored on the heap at checkpoint time, that token can still be restored from the image; therefore, obtain a new token after restore and revoke the old token according to the identity system's policy.

### Secret manager and KMS

A secret manager can issue database passwords or API tokens after the workload is authenticated. A KMS/HSM can keep private keys outside the JVM and only allow signing/decryption operations without exporting key material.

Prefer keeping secrets in a dedicated management system when supported by libraries. If the application must load secret bytes into the JVM, limit usage scope, storage duration, number of copies, and access permissions to heap dumps/checkpoint artifacts.

## 3. Distinguishing fresh startup from restore

The application needs a secret initialization path for both cases:

1. **Fresh JVM startup**: obtain workload identity, authenticate with the secret manager, fetch current secrets, and create initial clients.
2. **Restore from checkpoint**: the object graph is restored; then callbacks recover identity, fetch new credentials, and replace closed or expired clients.

Do not place secret-fetching logic only in a constructor or startup callback and assume the constructor will re-run after restore. Objects already existing on the heap are restored; their constructors do not automatically run again.

Conversely, do not place all initialization logic only in `afterRestore()`, because a normal fresh JVM run does not go through the restore callback.

An appropriate design is using a coordinating service with separated operations:

- `initializeForFreshStart()` for a fresh JVM.
- `prepareForCheckpoint()` to stop using and release credentials.
- `refreshAfterRestore()` to obtain new secrets.
- `isReady()` to indicate whether mandatory credentials and clients are ready.

The methods above are application-defined APIs, not CRaC APIs.

## 4. Registering resources and recovery order

CRaC provides `org.crac.Resource` with the callbacks `beforeCheckpoint(...)` and `afterRestore(...)`. A single resource can coordinate secret refreshing, or responsibility can be divided among the identity provider, secret provider, and client resources.

The dependency order must be explicit:

1. Recover workload identity or bootstrap credentials.
2. Connect to the secret manager/KMS and fetch new secrets.
3. Create required database pools, HTTP clients, broker clients, and TLS contexts.
4. Verify dependencies.
5. Open readiness/admission.

Do not rely on accidental component scan order or Resource registration order if the API/runtime does not guarantee it. A single coordinator can be used to orchestrate the dependency chain, or ordering/context mechanisms supported by CRaC and framework documentation can be used.

### Coordinator example

The following example illustrates the lifecycle. The interfaces are application abstractions; the actual implementation must use the environment's workload identity and secret manager.

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class SecretLifecycleResource implements Resource {

    public interface WorkloadIdentity {
        void refresh() throws Exception;
    }

    public interface SecretProvider {
        void refreshSecrets() throws Exception;
        void clearCachedSecrets();
    }

    public interface DependentClients {
        void closeForCheckpoint() throws Exception;
        void recreateAndVerify() throws Exception;
    }

    public interface ReadinessGate {
        void close();
        void open();
    }

    private final WorkloadIdentity identity;
    private final SecretProvider secrets;
    private final DependentClients clients;
    private final ReadinessGate readiness;

    public SecretLifecycleResource(
            WorkloadIdentity identity,
            SecretProvider secrets,
            DependentClients clients,
            ReadinessGate readiness) {
        this.identity = identity;
        this.secrets = secrets;
        this.clients = clients;
        this.readiness = readiness;
        Core.getGlobalContext().register(this);
    }

    public void initializeForFreshStart() throws Exception {
        readiness.close();
        identity.refresh();
        secrets.refreshSecrets();
        clients.recreateAndVerify();
        readiness.open();
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        readiness.close();
        clients.closeForCheckpoint();
        secrets.clearCachedSecrets();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        readiness.close();
        identity.refresh();
        secrets.refreshSecrets();
        clients.recreateAndVerify();
        readiness.open();
    }
}
~~~

This is a skeleton illustrating order, not a complete implementation for every secret manager. Operations must have timeouts, logging free of secrets, error cleanup, and bounded retry policies. If a step fails, readiness must remain closed; the serving gate must not be opened simply because a callback reached the end of a branch.

In a real application, determine behavior when a checkpoint is aborted after clients have closed and secret caches have been cleared. If rolling back to the ACTIVE state, the application must re-acquire credentials and recreate clients before opening admission. Do not assume there is an automatic `afterCheckpoint` callback to restore everything.

## 5. Limitations of erasing traces on the Java heap

In Java, assigning a variable to null only removes a reference. It does not overwrite the contents of the object that the reference used to point to. The Garbage Collector can reclaim the object when no live references remain, but when and how memory is reused is not precisely controlled by the application.

For example:

~~~java
String password = loadPassword();
usePassword(password);
password = null;
~~~

After the last line, the local variable no longer holds a reference to the String. However, that does not prove the String's contents have been erased from the heap. Another object, log buffer, exception, cache, or library may still hold a copy. Even when the object becomes unreachable, the old memory region may still contain bytes until overwritten.

### Strings are immutable

`String` is immutable. The application cannot directly modify the contents of a String after creation. Operations such as `replace()` or `toCharArray()` create new objects/buffers; they do not erase the original String.

For example:

~~~java
import java.util.Arrays;

String secret = readSecret();
char[] chars = secret.toCharArray();
Arrays.fill(chars, '\0');
~~~

The snippet above only overwrites the newly created char array. The String `secret` still contains the old contents until the memory is reused. If a secret manager API returns a String or a library requires passwords as Strings, zeroization capability is limited from the start.

For secret data, prefer APIs that accept overwritable `char[]` or `byte[]`, or APIs that perform operations using key handles without exporting key material. Even so, mutable buffers do not guarantee all copies have been erased.

### Overwriting arrays is only best effort

For example:

~~~java
char[] password = secretProvider.loadPassword();
try {
    authenticate(password);
} finally {
    Arrays.fill(password, '\0');
}
~~~

The array is overwritten in the finally block even if the operation fails. This is better practice than keeping credentials in Strings long-term, yet it still has limitations:

- The library receiving the array may have already copied its contents to another buffer.
- A JDBC driver or native library may hold a copy in native memory.
- An API wrapper may convert the array to a String.
- The compiler/JIT and runtime may create temporary copies during processing.
- The Garbage Collector may move the object or leave old copies in another heap region.
- The buffer may already have been serialized, logged, or written to diagnostic artifacts.

Therefore, do not claim `Arrays.fill()` has erased all traces. It only reduces the lifetime of the specific copy owned and overwritable by the application.

### Multiple copies of the same secret

A secret can appear in many places:

| Location | Why copies may remain |
|---|---|
| Configuration String | Immutable, contents cannot be overwritten |
| Original `char[]`/`byte[]` | Overwritable if the application still holds the reference |
| Library-created buffer | Application does not directly control it |
| JDBC/HTTP client | May retain internal credentials or headers |
| Exception | Message or cause may contain sensitive data |
| Logs/traces | May record headers, URLs, or payloads |
| Heap dump/checkpoint | May contain related objects and memory regions |
| Native memory | May retain copies off-heap |
| Direct ByteBuffer | Has its own lifecycle and release mechanism |

Good design needs to reduce the number of copies from the beginning. Avoid passing secrets through multiple layers of config, DTOs, String concatenation, exception messages, and logs. Pass secrets only to components that genuinely need them.

## 6. Direct buffers, native memory, and private keys

Not all sensitive data resides on the Java heap. Cryptographic libraries, TLS providers, JDBC drivers, or native SDKs may store key material in native memory, direct buffers, or internal structures.

### Direct ByteBuffer

`ByteBuffer.allocateDirect()` allocates off-heap memory. `clear()` or resetting position to 0 only changes buffer state; they do not overwrite contents.

If the application owns the buffer and the API permits writing, the used data region can be overwritten before release:

~~~java
ByteBuffer buffer = ByteBuffer.allocateDirect(secretLength);
try {
    buffer.put(secretBytes);
    buffer.flip();
    useSecretBuffer(buffer);
} finally {
    buffer.clear();
    while (buffer.hasRemaining()) {
        buffer.put((byte) 0);
    }
}
~~~

This snippet only illustrates overwriting a buffer owned by the application. It does not guarantee a library has not copied the data to another buffer, and not every direct buffer can be freed synchronously via public APIs. Avoid using internal JDK APIs to force deallocation without official support.

### Cryptographic key handles

For private keys, prefer an HSM, KMS, or cryptographic provider that keeps key material off-heap and only exposes signing/decryption operations. When a key cannot be exported, the JVM checkpoint does not need to contain the private key's bytes.

If a key is loaded into the JVM:

- Determine whether the provider retains native copies.
- Use destroy APIs if the implementation supports them.
- Do not call `getEncoded()` unless key bytes are truly required.
- Do not log keys, certificate bundles with private keys, or encoded forms.
- Recreate or acquire new handles after restore if required by the provider.

The `javax.security.auth.Destroyable` interface can provide `destroy()` and `isDestroyed()` for certain objects. Zeroization capability depends on the implementation; the method returning successfully does not by itself prove all copies in heap/native memory have vanished.

~~~java
import javax.security.auth.Destroyable;

if (credential instanceof Destroyable destroyable) {
    destroyable.destroy();
}
~~~

Read the specific provider's documentation to know which objects support destroy, what that operation does, and whether the object can be reused afterward.

## 7. Refreshing credentials and replacing clients

When secrets change after checkpoint, clients depending on old secrets must be replaced or updated via official APIs. Merely updating a field containing a password does not mean the connection pool or client is using the new credentials.

For example:

- A database pool may keep connections already authenticated with the old password.
- An HTTP client may keep an Authorization header in an interceptor.
- A broker client may keep an authenticated SASL session or connection.
- A TLS context may keep loaded certificates/keys.
- A cloud SDK may cache tokens and credential providers.

The recovery procedure should:

1. Close admission and ensure no requests are still using old clients.
2. Revoke or discard old clients via supported APIs.
3. Refresh workload identity.
4. Fetch new secrets/tokens from the trusted source.
5. Create new clients or pools with the new credentials.
6. Perform health checks and verify permissions.
7. Publish new clients only after checks succeed.
8. Open readiness.

If a library supports dynamic credential providers or token callbacks, prefer that mechanism. However, still verify whether the client refreshes properly after restore; a provider object remaining on the heap does not guarantee token caches or sockets have been refreshed.

### Rotation and revocation

A secret manager may rotate secrets while the application is paused. After restore, the application needs to use the current version and may need to revoke old tokens. Revocation timing must be coordinated with still-running replicas and the rollout process; revoking too early can disrupt instances that have not yet been updated.

For short-lived tokens, use a short TTL and refresh before expiration. After restore, do not trust an expiration timestamp on the heap if time or clock sources may differ; verify the token with the issuer or obtain a new token.

## 8. Keeping secrets out of logs and diagnostic artifacts

A common mistake is removing secrets from config yet accidentally writing them into logs:

~~~java
logger.debug("Connecting with password {}", password);
logger.error("Authentication failed for URL {}", jdbcUrl, exception);
~~~

JDBC URLs or exceptions can contain usernames/passwords or sensitive query parameters. Authorization headers, cookies, signed URLs, and request bodies can also contain credentials.

Principles:

- Do not log passwords, tokens, private keys, or secret bytes.
- Redact sensitive headers/cookies and query parameters.
- Do not include secrets in exception messages or assertion output.
- Do not enable wire/debug logging in production without redaction.
- Check APM, tracing, metrics labels, and crash reporters.
- Restrict access permissions to logs, heap dumps, JFR, and core dumps.
- Set appropriate retention and delete artifacts according to policy.

Heap dumps and core dumps can contain more sensitive data than regular logs. Enabling dump features requires controls over permissions, storage locations, encryption, retention, and investigative access procedures.

## 9. Limitations of erasing traces before checkpoint

Some applications attempt to erase secrets before checkpoint by:

- Setting fields holding secrets to null.
- Overwriting `char[]` or `byte[]`.
- Calling destroy on credential objects.
- Closing clients and pools.
- Clearing caches or sessions.

These steps are helpful, yet they do not produce a guarantee that the checkpoint image contains no secret traces.

### Why can complete erasure not be guaranteed?

**Immutable objects:** Strings cannot be overwritten directly. If a library created a String, the application has no standard API to alter its contents.

**Copies outside control:** Drivers, frameworks, providers, or native code may have copied secrets to other structures.

**Garbage collection:** GC manages object lifetimes but does not commit to zeroizing immediately when an object becomes unreachable. Compaction can move data and leave old copies in memory.

**JIT and runtime:** The runtime may hold temporary values or create internal representations that the application cannot fully observe.

**Native/direct memory:** Off-heap data has its own lifecycle and may not be erased by operations on Java objects.

**Already created artifacts:** If secrets have already been written to a checkpoint, heap dump, log, or temporary file, clearing a field in the process afterward does not alter the already created artifact.

### Removing a reference is not erasing data

~~~java
credential = null;
~~~

The statement above only removes one reference. It does not:

- Overwrite the object's bytes.
- Remove other references.
- Force GC to run immediately.
- Erase native or direct buffer copies.
- Remove secrets from an already created checkpoint.

Do not use `System.gc()` as a secret erasure mechanism. GC may not run immediately, does not commit to overwriting memory, and can cause pauses. It is not a zeroization API.

### Erasing after checkpoint does not fix the image either

If the application creates a checkpoint while secrets are still on the heap and only clears variables in the continuing execution, the saved checkpoint image can still contain the secrets. Preparation must happen before calling checkpoint, and created artifacts must be verified according to an appropriate process.

Do not open a checkpoint image as a normal file to search for password strings and patch bytes. Modifying image contents can corrupt the structure or integrity of the checkpoint and is not a safe method of removing secrets.

## 10. How to reduce the amount of secrets entering the heap image

Since zeroization cannot be guaranteed absolutely, prioritize minimizing secrets present at checkpoint time.

### Late loading

Fetch secrets only right before a client needs to use them. Do not load all credentials at application startup if some are only used for rare tasks or within a single request.

### Using short-lived credentials

Prefer tokens with short TTLs, narrow scopes, and revocation capability. Avoid long-lived credentials with broad permissions kept in singletons throughout the JVM lifecycle.

### Keeping keys outside the JVM

Use KMS/HSM or providers supporting key-handle operations so private keys do not need to be exported onto the heap.

### Reducing the number of copies

- Prefer `char[]`/`byte[]` if APIs allow.
- Avoid converting to Strings, DTOs, or concatenation.
- Do not copy buffers unnecessarily.
- Do not keep credentials in caches or static fields.
- Release application-owned buffers immediately after use.
- Close old clients via official APIs before checkpoint.

### Separating secrets from checkpoint configuration

Do not embed secrets in:

- JVM command line or system properties if avoidable.
- Configuration files packaged with the image.
- Container environment variables if a better identity mechanism exists.
- Logs, traces, metrics, or exceptions.
- Checkpoint metadata/manifest.

Environment variables are not automatically safer than files; values can appear in the process environment, diagnostic output, or the heap after the application reads them. Choose the secret delivery channel based on the threat model and platform capabilities.

## 11. Example of managing byte[] with a short lifetime

If a secret manager API returns `byte[]` and the client can use it directly within a synchronous scope, lifetime can be bounded with try/finally.

~~~java
import java.util.Arrays;

public final class SecretUse {

    @FunctionalInterface
    public interface SecretOperation<T> {
        T execute(byte[] secret) throws Exception;
    }

    private SecretUse() {
    }

    public static <T> T withSecret(
            SecretLoader loader,
            SecretOperation<T> operation) throws Exception {
        byte[] secret = loader.load();
        try {
            return operation.execute(secret);
        } finally {
            Arrays.fill(secret, (byte) 0);
        }
    }

    public interface SecretLoader {
        byte[] load() throws Exception;
    }
}
~~~

This code overwrites the buffer returned by loader after operation completes. The critical conditions are that loader transfers ownership of the buffer to the caller and operation does not retain a long-lived reference or copy. If the client library copies the secret, that copy must be managed according to the library's API.

Do not invoke an async operation and overwrite the buffer immediately when the method returns if the background task is still using the array. With asynchronous processing, an explicit lifecycle is needed to know when all consumers have finished.

### APIs accepting String

If a library only accepts String, understand that creating a String creates an immutable copy that the application cannot zeroize directly. Do not create extra Strings just to format or log credentials. If this is a critical component, consider alternative APIs supporting mutable buffers or credential providers.

## 12. Handling errors when the secret manager is unavailable

After restore, the secret manager or identity endpoint may not be ready yet. The application must keep readiness false and retry within a bounded time budget.

Error classification:

| Error | Handling |
|---|---|
| Identity endpoint temporarily unreachable | Retry with backoff and jitter |
| Secret manager timeout | Retry with a deadline, record error code without secrets |
| Workload identity rejected | Do not open readiness; report authentication error |
| Secret already rotated | Fetch current version and create new client |
| Secret revoked | Stop using old credentials, request re-issuance |
| Insufficient scope | Fail explicitly and update policy |
| KMS/HSM unavailable | Keep key-dependent features in a not-ready state |

Do not retry indefinitely inside a callback if doing so leaves restore hanging without a result. You can wait boundedly in `afterRestore()` or start a recovery worker while keeping readiness false. The strategy must match how the orchestrator handles not-ready instances.

Do not log full requests or tokens to diagnose authentication errors. Use correlation IDs, issuer, audience, secret version ID, and permitted error codes.

## 13. Example Resource reloading secrets after restore

The example below illustrates a resource owning a secret buffer as `byte[]`. All operations using the secret go through a synchronized method so the resource can wait for in-progress operations to finish before overwriting the buffer.

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

import java.util.Arrays;

public final class SecretMaterialResource implements Resource {

    @FunctionalInterface
    public interface SecretSource {
        byte[] loadCurrentSecret() throws Exception;
    }

    @FunctionalInterface
    public interface SecretOperation<T> {
        T apply(byte[] secret) throws Exception;
    }

    private final SecretSource source;
    private byte[] secret;
    private boolean ready;

    public SecretMaterialResource(SecretSource source) throws Exception {
        this.source = source;
        this.secret = source.loadCurrentSecret();
        if (secret == null || secret.length == 0) {
            throw new IllegalStateException("Secret source returned no secret");
        }
        this.ready = true;
        Core.getGlobalContext().register(this);
    }

    public synchronized <T> T withSecret(SecretOperation<T> operation)
            throws Exception {
        if (!ready || secret == null) {
            throw new IllegalStateException("Secret is not ready");
        }
        return operation.apply(secret);
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) {
        ready = false;
        clearSecret();
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        byte[] candidate = source.loadCurrentSecret();
        if (candidate == null || candidate.length == 0) {
            if (candidate != null) {
                Arrays.fill(candidate, (byte) 0);
            }
            throw new IllegalStateException("Secret source returned no secret");
        }
        secret = candidate;
        ready = true;
    }

    public synchronized void resumeAfterAbortedCheckpoint()
            throws Exception {
        if (secret == null) {
            secret = source.loadCurrentSecret();
        }
        ready = secret != null && secret.length > 0;
        if (!ready) {
            if (secret != null) {
                Arrays.fill(secret, (byte) 0);
                secret = null;
            }
            throw new IllegalStateException("Cannot reload secret");
        }
    }

    private void clearSecret() {
        if (secret != null) {
            Arrays.fill(secret, (byte) 0);
            secret = null;
        }
    }
}
~~~

This pattern demonstrates several points:

- A fresh JVM obtains the secret in the constructor; the fresh startup path does not depend on the restore callback.
- Before checkpoint, the resource disables secret usage and overwrites the buffer it owns.
- After restore, the resource obtains the current secret from a trusted source.
- If the source cannot supply a secret, the callback fails and the application must not open readiness.
- There is a dedicated method illustrating rollback if the checkpoint is aborted and the application continues running.

This is still only best-effort zeroization. SecretOperation receives a reference to the internal array; the caller's contract must specify not retaining references, not modifying the array, and not creating unnecessary copies. In a real system, close admission and drain requests before callbacks run. Synchronization on the resource does not replace full-application draining or transaction management.

If a library API forces creating a String or keeps credential copies, the resource cannot erase those copies. Use credential provider/secret handle APIs supported by the library, or close and recreate clients to reduce how long old credentials are retained.

## 14. Protecting checkpoint artifacts as confidential data

Even when the application refreshes secrets after restore, old checkpoint images may still contain previously loaded credentials. Therefore, artifacts must be protected according to the sensitivity level of heap data.

### Access permissions and storage

- Restrict image read permissions to services and operators that genuinely need them.
- Do not place images in public directories, public artifact repositories, or open buckets.
- Encrypt at rest and when transferring over the network.
- Protect checksums, manifests, and backups; provenance signatures do not replace encryption.
- Use appropriately short retention and delete artifacts through a managed process.
- Restrict access permissions to heap dumps, core dumps, and JFR recordings.
- Do not put checkpoints into Git, log archives, or Docker build contexts.

### Encryption key management

If encrypting images, decryption keys must be managed separately from artifacts. Do not place decryption keys in the same archive or manifest. Prefer KMS/HSM or a key management system with auditing, rotation, and access policies.

Encryption at rest protects data stored on storage, but does not protect an image from a process or operator that already has decryption permissions. IAM controls, artifact access permissions, and auditing remain necessary.

### Stale secrets in images

If a checkpoint is discovered to contain exposed or no-longer-permitted secrets:

1. Revoke or rotate the credentials at the issuer/secret manager.
2. Identify all image copies, archives, caches, and backups.
3. Prevent old images from continuing to be restored.
4. Delete or isolate artifacts according to retention and incident response procedures.
5. Create a new checkpoint after the application has switched to current credentials.
6. Check whether logs, heap dumps, and diagnostic artifacts contain the same secrets.

Do not delete only the primary checkpoint file if archives or backup copies still exist.

## 15. Testing the secret lifecycle around checkpoints

Testing needs to verify both things: new secrets are actually used after restore and old secrets are no longer used by active clients.

### Basic scenario

1. Start a fresh application and confirm workload identity obtains the secret.
2. Confirm database, HTTP, or broker clients are created with current credentials.
3. Record non-sensitive secret version ID or key ID; do not record secret values.
4. Close admission and drain requests using credentials.
5. Run checkpoint preparation callbacks and confirm application-owned buffers are handled.
6. Create the checkpoint.
7. Rotate secrets in the secret manager or expire credentials in the test environment.
8. Restore the image.
9. Confirm callbacks fetch new credentials and recreate clients.
10. Confirm health checks and real requests succeed.
11. Confirm readiness opens only after all mandatory dependencies are ready.
12. Confirm no logs or telemetry contain secrets.

### Scenarios to test

| Scenario | Expected result |
|---|---|
| Secret manager available | New secret is fetched and client works |
| Secret manager temporarily unreachable | Bounded retry or recovery worker; readiness false |
| Credentials rotated before restore | New client uses current version |
| Old credentials revoked | Old client is not reused |
| Workload identity expired | Identity is refreshed or restore does not open readiness |
| Client creation fails after fetching secret | Candidate is cleaned up, readiness false |
| Checkpoint aborted | Rollback re-acquires secrets and clients before opening admission |
| Library retains secret copy | Documented in threat model; use alternative API if available |
| Secret resides in a String | Do not claim zeroization; reduce scope and lifetime |
| Multiple instances restore simultaneously | Secret manager is not overloaded; retries have jitter |
| Heap dump/diagnostics generated | Artifacts are protected and not leaked beyond permitted roles |

### Verifying values without printing secrets

Tests should verify:

- Secret version ID or credential generation.
- Client can connect to dependencies.
- Old credentials are rejected after rotation if policy requires.
- Application-owned buffers were overwritten in the test harness.
- No secrets appear in collected logs.

Do not print secrets to "confirm" tests. If checking overwritten buffers is needed, use internal assertions on non-sensitive test copies or verify buffers generated by fixtures; do not generate logs containing real values.

## 16. Common misconceptions

| Misconception | Accurate understanding |
|---|---|
| Setting a String to null erases the password. | Only drops one reference; the String and copies may remain on the heap. |
| Calling System.gc() erases secrets. | GC does not guarantee zeroization or reclamation timing. |
| Arrays.fill() erases all copies. | Only overwrites the specific array owned by the application. |
| Secret was cleared after checkpoint so the image is safe. | The already created image may still contain the old secret. |
| Restore re-runs constructors. | The object graph is restored; use afterRestore to refresh required state. |
| A secret manager client still on the heap is usable. | Sockets, identity tokens, and caches may have expired. |
| A token unexpired by timestamp is definitely valid. | The issuer may revoke it; verification or fetching a new token is needed. |
| Environment variables are always safer than secret files. | Both can be read or copied into the heap/diagnostic data. |
| HSM/KMS eliminates all secret risks. | Key handles reduce exporting key material, but identity, policy, and signing operations still need protection. |
| Encrypting the artifact is enough. | Key management, IAM, auditing, retention, and protecting decrypted copies are needed. |

## 17. Implementation checklist

### Before checkpoint

- [ ] Close admission and drain all requests/jobs using credentials.
- [ ] Close clients, pools, or sessions according to library-supported lifecycles.
- [ ] Clear secret caches and overwrite application-owned buffers where appropriate.
- [ ] Do not assume Strings, native memory, or library copies have been zeroized.
- [ ] Keep tokens, passwords, and private keys out of logs/exceptions.
- [ ] Define rollback if checkpoint is aborted after secrets have been released.

### After restore

- [ ] Refresh workload identity or bootstrap credentials.
- [ ] Connect to secret manager/KMS using current identity.
- [ ] Fetch current secrets/tokens with appropriate scope and TTL.
- [ ] Recreate secret-dependent clients/pools/TLS contexts.
- [ ] Verify real operations and access permissions.
- [ ] Keep readiness false while identity or secrets are not ready.
- [ ] Do not publish unverified clients.

### Protecting artifacts and testing

- [ ] Treat checkpoints as sensitive data that may contain secrets.
- [ ] Encrypt images at rest/in transit and manage keys separately.
- [ ] Restrict read permissions, backups, heap dumps, and diagnostic artifacts.
- [ ] Have a rotation/revocation procedure when old images contain invalid credentials.
- [ ] Tested restore after secrets have been rotated or revoked.
- [ ] Checked that logs/traces/metrics do not expose secrets.
- [ ] Documented zeroization limitations of each library/provider.

Loading or refreshing secrets after restore reduces the risk of old credentials being packaged and continuing to be used from the heap image. However, Java provides no portable way to reliably erase every secret copy from the heap, native memory, and created artifacts. Minimize secrets present at checkpoint time, use workload identities and short-lived credentials, refresh clients in lifecycle order, overwrite application-owned buffers as a best-effort measure, and protect checkpoint artifacts as sensitive data.
