# Identifying secrets and sensitive data that may exist in the memory image

CRaC (Coordinated Restore at Checkpoint) creates a state image of a Java process so that the process can be restored later. A checkpoint image can contain the heap, stack, thread state, and other memory regions supported by the runtime's checkpoint mechanism. If the process is holding passwords, access tokens, encryption keys, personal data, or request contents in memory, that data can appear in the image.

Therefore, a checkpoint image needs to be treated as a sensitive artifact equivalent to the memory of a running process. Protecting the application at runtime is not enough; control is needed when creating, storing, copying, transferring, restoring, backing up, and deleting the image.

## 1. Why can a checkpoint image contain secrets?

A Java application commonly loads sensitive data into memory to perform work. Data can exist in many layers:

- Heap: objects, Strings, byte arrays, configuration, caches, and sessions.
- Thread stacks: local variables, method parameters, and active references.
- Buffers: ByteBuffers, direct buffers, buffers from networking or JDBC libraries.
- Native memory: data allocated by JNI/JNA, TLS providers, drivers, or native libraries.
- ThreadLocals and static fields: tokens, user context, credentials, or long-lived cached data.
- Memory-mapped regions: file contents mapped into the address space.
- Library state: TLS sessions, authentication contexts, connection pools, or credential caches.

If a checkpoint is created while this data still resides in memory regions being snapshotted, the image can retain copies of it. The fact that an object is no longer used by the application does not mean its bytes have been erased from memory. The Garbage Collector can reclaim the object logically, but it does not guarantee immediately overwriting the old memory region.

A checkpoint image can thus contain more than just the fields the application actively considers data to persist. Temporary copies, data in buffers, and internal library state also need to be examined.

### Example of a token on the heap

~~~java
public final class ApiClient {
    private final String accessToken;

    public ApiClient(String accessToken) {
        this.accessToken = accessToken;
    }

    public void callService() {
        // Authorization header is constructed from accessToken.
    }
}
~~~

If ApiClient is still live at checkpoint time, accessToken remains part of the object's state. The memory image may contain the token string and related copies created during request processing.

If the token grants access to external systems, anyone able to read and restore the image may be able to use that token, depending on its expiration, scope, and authentication policy.

## 2. Types of sensitive data to identify

Not only passwords are considered secrets. Before creating a checkpoint, compile an inventory of data whose exposure could impact users, systems, or the organization.

| Data group | Examples | Exposure risk |
|---|---|---|
| Passwords and credentials | Database password, API key, SMTP password | Unauthorized access to services |
| Tokens | OAuth access/refresh token, JWT, session cookie | Impersonation of users or workloads |
| Cryptographic keys | Private key, symmetric key, data encryption key | Decryption of data or signature forgery |
| TLS information | Key material, session secret, client certificate private key | Connection impersonation or decryption depending on context |
| Personal data | Name, email, phone number, address, identifier | Privacy violation |
| Authentication data | Session, MFA state, reset token | Session hijacking or authentication bypass |
| Business data | Customer profiles, transactions, document contents | Exposure of business information or protected data |
| Request contents | Request body, headers, query parameters | Exposure of information sent to APIs |
| Cached data | User profile, authorization decision, query result | Data leakage across tenants or users |
| Debug data | Stack trace, diagnostic snapshot, request dump | Disclosure of configuration, data, or credentials |

Both encrypted and decrypted data need to be evaluated. Ciphertext may not be as sensitive as plaintext if the key is protected independently, but having the decryption key in the same image can negate the benefit of encryption.

### Static secrets and time-bound secrets

We can distinguish:

- Long-lived secrets: private keys, master keys, database credentials, or API keys that change infrequently.
- Short-lived secrets: access tokens, session tokens, signed URLs, or credentials with a short TTL.
- Session-scoped secrets: TLS session state, authentication context, or tokens tied to a single request.
- Temporary sensitive data: a newly received password, request body, decrypted data, or file contents currently being processed.

Short-lived secrets can still be dangerous if the checkpoint image is stored longer than the token's lifetime, or if the token can be refreshed using another refresh token that is also in the image.

## 3. Sources through which secrets can enter Java memory

An effective inventory needs to locate the data sources, how they are loaded, and where they are stored.

### Environment variables

Applications often read credentials from the environment:

~~~java
String password = System.getenv("DB_PASSWORD");
~~~

Environment variables help avoid hard-coding secrets in source code, but once read, the value may be held in a String or configuration object. The process environment may also be saved in process state depending on the snapshot mechanism.

One should not conclude that using environment variables means secrets will not appear in the checkpoint image. Check how the runtime and deployment environment handle the process environment, and also restrict access permissions to the image.

### System properties and command-line arguments

Credentials can be passed via:

~~~bash
java -Dapi.token=secret-value -jar app.jar
~~~

Or passed via command-line arguments. These values can appear in process metadata, startup logs, diagnostic output, or snapshotted state.

Do not pass secrets directly on the command line if safer options exist. Prefer a secret manager, restricted file mounts, or workload identity, depending on the platform.

### Configuration files and binding objects

Spring Boot or another framework can bind configuration values into beans:

~~~java
@ConfigurationProperties(prefix = "remote.api")
public class RemoteApiProperties {
    private String token;

    public String getToken() {
        return token;
    }

    public void setToken(String token) {
        this.token = token;
    }
}
~~~

After binding, token resides in an object that lives alongside the ApplicationContext. If the bean is kept on the heap during checkpoint, the value may be saved in the image.

External configuration files or mounted secrets do not make the loaded value disappear from the heap. The lifecycle of objects holding secrets needs to be designed.

### Requests, sessions, and caches

A request can introduce sensitive data into:

- Controller parameters and DTOs.
- Authentication principals.
- SecurityContext.
- HTTP headers and body buffers.
- Session objects.
- Caches or retry queues.
- Exception messages and diagnostic contexts.

A completed request can still leave data behind in caches, ThreadLocals, or objects referenced from singletons. Contexts should be cleared according to the request lifecycle, avoiding holding personal data longer than necessary.

### JDBC, HTTP, and TLS clients

Connection pools, HTTP clients, and the TLS stack can hold credentials, tokens, cookies, session state, or buffers. Closing clients before checkpoint helps handle sockets and threads, but does not by itself guarantee that all copies of secrets on the heap have been erased.

If the application needs to reconnect after restore, create new clients from re-issued or re-verified credentials after restore.

### Native libraries and direct buffers

Native libraries can hold key material or plaintext in memory outside the Java heap. DirectByteBuffers can also contain sensitive data.

Do not inventory only Java fields. Identify crypto, TLS, compression, database driver, JNI/JNA, and SDK libraries that may hold data in native memory.

## 4. String, byte[], and the limitations of erasing secrets

In Java, String is immutable. Once a password is created as a String, the application cannot overwrite the content of that String itself through public APIs.

~~~java
String password = obtainPassword();
authenticate(password);
password = null;
~~~

Assigning null only drops the reference from the password variable. It does not erase the String's bytes from the heap immediately. The Garbage Collector may reclaim the object later, but there is no guarantee on timing or memory overwriting.

In addition, a secret may already have been copied when:

- Converting from byte[] to String.
- Concatenating strings to build headers or URLs.
- Writing to logs or exceptions.
- Binding into multiple configuration objects.
- Passing into buffers or native libraries.
- Passing through APIs that require String.

### Using mutable arrays when the API supports them

If the API allows, secrets can be held in char[] or byte[] and overwritten after use:

~~~java
char[] password = secretProvider.readPassword();

try {
    authenticate(password);
} finally {
    Arrays.fill(password, '\0');
}
~~~

With byte[]:

~~~java
byte[] keyBytes = secretProvider.readKey();

try {
    useKey(keyBytes);
} finally {
    Arrays.fill(keyBytes, (byte) 0);
}
~~~

This is a measure to reduce data lifetime, not an absolute erasure guarantee. The JVM, JIT compiler, libraries, and called APIs may create other copies. If the data has already been converted into a String, clearing the original array does not erase the String copy.

Do not call clear() on a ByteBuffer and assume the data has been erased. clear() only resets the buffer's position and limit; the byte contents may still remain. To overwrite a buffer, a put loop or equivalent operation can be used, though direct buffers and native copies still need separate evaluation.

### Avoiding turning secrets into concatenated strings

Avoid building strings containing credentials for convenient logging or configuration:

~~~java
String authorization = "Bearer " + token;
logger.debug("Authorization: {}", authorization);
~~~

The Authorization header should be passed directly to the HTTP client and must be excluded from logs. Do not put tokens into URL query parameters because URLs are often recorded in access logs, proxy logs, or tracing.

### Do not implement custom cryptographic zeroization

If key material needs protection, prefer crypto APIs or providers that have proper key management mechanisms. Do not write a homegrown utility and claim it guarantees erasing all copies in the JVM.

For non-exportable keys, an HSM or KMS can keep the key outside the process. The application only holds a handle or permission to invoke signing/decryption operations. This is often a way to reduce the amount of sensitive key material in the checkpoint image.

## 5. Sensitivity level of a checkpoint image

Assume that someone with read access to the memory image can find part of the data the process accessed near checkpoint time. The actual level depends on the runtime, snapshotted memory regions, protection mechanisms, and how secrets are managed.

A checkpoint image should be classified and protected at least according to the highest sensitivity level of data that may exist in process memory.

For example:

~~~text
Running application
   |
   +-- Database credential
   +-- OAuth token
   +-- TLS key material
   +-- Customer data
   +-- Request/session state
   |
   v
Checkpoint image
   |
   +-- May contain the memory regions above
   |
   v
Storage / copy / transfer / restore
~~~

If an image is treated as a normal deployment artifact, it may be copied to registries, object storage, backups, or CI/CD environments with broader permissions than necessary. This creates additional leak paths.

### Locations that need protection

Inventory the entire artifact lifecycle:

- Temporary directories where the runtime creates the checkpoint.
- Main checkpoint directory.
- Copies used for restore.
- Backups and snapshots of volumes containing checkpoints.
- Object storage or artifact registries.
- Transfer paths between the creating node and the restoring node.
- Caches of the deployment system.
- Logs, diagnostic bundles, and investigation support files.
- Copies in test or staging environments.

Do not protect only the original directory. A copy downloaded to a personal machine or attached to a ticket is still a copy of sensitive data.

## 6. Encryption and key management for checkpoint images

If a checkpoint image is stored on disk or transferred over the network, it needs to be encrypted according to the system's security policy.

Important principles:

1. Encrypt data at rest using a platform-supported mechanism or an appropriate artifact encryption layer.
2. Use TLS or a secure transport channel when transferring images.
3. Restrict read, write, restore, and delete permissions by role.
4. Separate image management permissions from decryption key usage permissions.
5. Store encryption keys in a KMS/HSM or secret manager independent from the image.
6. Monitor audit logs for downloads, copies, and restores.
7. Maintain an expiration and secure deletion policy for images and backups.

Do not assume every CRaC distribution automatically encrypts checkpoint images. Verify the actual capabilities of the runtime, filesystem, and storage provider. If the platform does not provide adequate encryption, add an artifact protection layer before saving or distributing.

### Do not place decryption keys inside the image itself

If the image is encrypted, yet the decryption key is also in the heap or a file packaged with the image, anyone who has the image can obtain both components.

The decryption key needs to be supplied from an independent source after the workload is authenticated. KMS, HSM, workload identity, or policy-based key release mechanisms can be used.

### Access control

Apply least privilege:

- Only necessary service accounts are permitted to read the image.
- Only authorized nodes or workloads are permitted to restore.
- Developers do not have permission to download production images by default.
- Do not use public buckets or registries.
- Separate permissions for image creation, approval, distribution, and deletion.
- Record who accessed the image and when.

If an image contains production credentials, do not restore it into a less trusted environment merely for debugging. Restoring can bring those secrets into the process memory of the new environment.

## 7. Reducing sensitive data before checkpoint

The best way to reduce risk is to not leave unnecessary data in memory at the time the image is created.

A preparation procedure may include:

1. Stop accepting new requests and work.
2. Drain in-flight requests and complete transactions.
3. Clear unnecessary request contexts, security contexts, and ThreadLocals.
4. Evict personal data from caches if the caches can be rebuilt.
5. Stop retry queues or buffers containing sensitive payloads.
6. Close clients holding old sessions or tokens.
7. Overwrite mutable byte/char arrays that can be safely cleared.
8. Remove secrets needed after restore from the heap and prepare a re-issuance mechanism.
9. Inspect logs, diagnostic buffers, and temporary objects.
10. Create the checkpoint only when the application is in the prepared state.

Do not erase business data needed to restore correctness. Distinguish state necessary to resume work from temporary credentials or payloads that can be reloaded.

### Do not checkpoint in the middle of a sensitive operation

For example, if the application is processing a password change, token reset, or payment request, the heap may contain both input data and transaction state. Complete or cancel the operation according to business rules before checkpointing.

For requests that cannot complete quickly, move them to a durable queue or persist a minimal job state, without storing raw credentials or sensitive payloads unless necessary.

### Cleaning up ThreadLocal

ThreadLocals can hold user context or credentials on a thread pool longer than a request's duration:

~~~java
try {
    currentUser.set(userContext);
    processRequest();
} finally {
    currentUser.remove();
}
~~~

Always call remove() in finally. Otherwise, a reused thread may retain data from the previous request, and that data may appear in the checkpoint image.

## 8. Re-acquiring secrets after restore

For credentials needed to continue connections, it is usually best to re-acquire them after restore rather than relying on old values stored in the heap.

A high-level flow:

~~~text
Restore process
      |
      v
Keep request gate closed
      |
      v
Authenticate workload identity
      |
      v
Obtain new secret/token from provider
      |
      v
Recreate client / connection pool
      |
      v
Verify dependencies and permissions
      |
      v
Clear temporary secret buffer
      |
      v
Open workers and request listener
~~~

This approach handles credentials that expired or were rotated while the image was waiting to be restored.

### Using a SecretProvider abstraction

Secret retrieval can be separated from the service using it:

~~~java
public interface SecretProvider {
    char[] readSecret(String secretName) throws Exception;
}
~~~

The service receives the provider and requests the secret when needed:

~~~java
public final class RemoteClientFactory {
    private final SecretProvider secrets;

    public RemoteClientFactory(SecretProvider secrets) {
        this.secrets = secrets;
    }

    public RemoteClient create() throws Exception {
        char[] token = secrets.readSecret("remote-api-token");

        try {
            return RemoteClient.connect(token);
        } finally {
            Arrays.fill(token, '\0');
        }
    }
}
~~~

RemoteClient.connect() is an illustrative API. In practice, check whether the library copies the token into a String or keeps the token in an internal object. Clearing the input array does not automatically erase copies that the client has already created.

### Do not cache secrets longer than necessary

If a client must keep a token to refresh or authenticate requests, define its lifecycle and rotation capability clearly. You can use a provider capable of swapping credentials, a client wrapper, or a factory that creates a new client when the secret changes.

Do not let multiple singletons hold copies of a credential simply because injecting a String is convenient. Reduce the number of places storing secrets and avoid passing secrets through layers that do not need to know them.

## 9. CRaC Resource for sensitive data

CRaC provides the Resource interface with two main callbacks:

- beforeCheckpoint(): prepares resources before creating the checkpoint.
- afterRestore(): recreates or verifies resources after restore.

A resource managing a client can close the old client and clear temporary secret buffers before checkpoint, then obtain a new secret and create the client after restore.

~~~java
import java.util.Arrays;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ProtectedClientResource implements Resource {
    private final SecretProvider secretProvider;
    private RemoteClient client;
    private char[] temporarySecret;

    public ProtectedClientResource(
            SecretProvider secretProvider) throws Exception {
        this.secretProvider = secretProvider;
        this.client = createClient();
        Core.getGlobalContext().register(this);
    }

    private RemoteClient createClient() throws Exception {
        char[] secret = secretProvider.readSecret("remote-api-token");

        try {
            return RemoteClient.connect(secret);
        } finally {
            Arrays.fill(secret, '\0');
        }
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        if (client != null) {
            client.close();
            client = null;
        }

        clearTemporarySecret();
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        client = createClient();
    }

    public synchronized void recoverAfterAbortedCheckpoint()
            throws Exception {
        if (client == null) {
            client = createClient();
        }
    }

    private void clearTemporarySecret() {
        if (temporarySecret != null) {
            Arrays.fill(temporarySecret, '\0');
            temporarySecret = null;
        }
    }
}
~~~

ProtectedClientResource is a conceptual example. RemoteClient, SecretProvider, and client creation need to be replaced with real implementations. If the client holds tokens internally, verify whether the close() API clears or releases sensitive state; do not assume close() equals zeroization.

In the example, credentials are read in the factory and the input array is overwritten after calling connect(). If the library creates String copies or native buffers, the application needs to evaluate that separately. For cryptographic keys, prefer a provider that keeps keys outside the process if possible.

### Distinguishing restore from an aborted checkpoint

If the checkpoint succeeds and the process is restored, afterRestore() runs to obtain new credentials and create a new client.

If the checkpoint is aborted, the original process continues. afterRestore() is not a rollback callback. If beforeCheckpoint() already closed the client, the application needs to recreate the client in the recovery branch.

When the application calls Core.checkpointRestore(), it can catch CheckpointException:

~~~java
try {
    Core.checkpointRestore();
    // Continue in the restored process.
} catch (CheckpointException checkpointFailure) {
    try {
        protectedClient.recoverAfterAbortedCheckpoint();
    } catch (Exception recoveryFailure) {
        checkpointFailure.addSuppressed(recoveryFailure);
        markApplicationNotReady();
    }

    throw checkpointFailure;
} catch (RestoreException restoreFailure) {
    // This is an error in the restored process.
    markApplicationNotReady();
    throw restoreFailure;
}
~~~

If the checkpoint is requested externally via jcmd, the application flow calling the API does not have this catch block. Therefore, do not delete the only credential or close resources in a way that prevents the original process from recovering, unless an independent recovery mechanism has been designed and tested.

No afterRestore() callback runs automatically simply because a checkpoint was aborted. This is important when deciding whether to clear secrets or close clients in beforeCheckpoint().

## 10. Secret managers, workload identity, and KMS

A good design does not need to store all long-lived credentials in the image. Instead, the workload can authenticate with a secret-issuing system after restore.

Common options:

- Secret manager: issues database passwords, API tokens, or secrets according to policy.
- Workload identity: authenticates the workload based on a service account or runtime identity instead of storing static keys.
- KMS: performs encryption/decryption operations using externally managed keys.
- HSM: keeps private keys in hardware or a key-protection service.
- Short-lived credentials: tokens with a short TTL and minimal scope.
- Certificate rotation: issues new certificates when an instance is created or when a certificate is about to expire.

### Workload identity

Instead of packaging a long-lived access key in the image, the workload can use a platform-issued identity. After restore, it re-authenticates and obtains short-lived credentials.

Ensure that the identity token or service account credential used for bootstrapping is not exposed in the image. If the bootstrap credential also sits on the heap, the risk is merely shifted from the primary token to the bootstrap token.

### KMS/HSM

If a private key does not need to leave the KMS/HSM, the application only holds a key reference and calls the service to sign or decrypt. The checkpoint image then does not need to contain the raw private key.

It is still necessary to protect the access token or workload identity that allows calling the KMS. Restrict permissions by key, operation, workload identity, and environment.

## 11. Credentials may expire or rotate during checkpoint

An image may be stored for many hours or days. During that interval:

- Database passwords may be rotated.
- OAuth access tokens may expire.
- Refresh tokens may be revoked.
- TLS certificates may expire or be replaced.
- API keys may be disabled after an incident.
- User sessions may be logged out or revoked.
- Workload permissions may change.

If restore uses an old credential, connections may fail or, worse, continue using a credential that should have been revoked under a policy not yet properly enforced.

Non-sensitive metadata such as secret version, key ID, certificate serial, or when the credential was issued should be saved. After restore, fetch the current credential and verify version/policy before opening traffic.

Do not store raw secrets in the checkpoint manifest. The manifest should only have the secret name, version reference, or identifier needed to retrieve the data again.

### Rotation and revocation

When a checkpoint image is exposed or no longer trusted:

1. Identify the secrets that may have been inside the image.
2. Revoke or rotate the corresponding credentials.
3. Invalidate tokens/sessions that could be reused.
4. Identify all image copies and backups.
5. Block restores from the untrusted image.
6. Create a new checkpoint image after credentials have been re-issued.
7. Record audit events and check for anomalous access.

Deleting the image does not replace rotating secrets if there is any possibility the image was copied.

## 12. Logs, tracing, and diagnostic data

Secrets can be copied out of the heap via logging and observability.

Locations to check:

- Authorization header.
- Cookie and Set-Cookie.
- Query parameters with tokens.
- Request/response bodies.
- JDBC URLs containing credentials.
- Exception messages from drivers or SDKs.
- HTTP client wire logs.
- Distributed trace baggage or span attributes.
- Debug dumps and heap dumps.
- Metrics labels containing sensitive identifier values.

Do not log raw requests or entire configuration objects. Use an allowlist for fields permitted to be logged and redact sensitive headers/fields before sending logs or traces.

If a checkpoint image is created after debug logging is enabled, buffers or diagnostic objects may hold sensitive data longer. Disable request/body dumping in production unless there is an approved and controlled need.

## 13. Detecting secrets in images and pre-distribution checks

Inspecting images can help detect unexpected sensitive data, but must be performed in a controlled environment.

Applicable measures:

- Maintain a secret inventory for the application and libraries.
- Scan artifacts or memory regions using approved tools.
- Use canary secrets in a test environment to confirm whether data is retained in the image.
- Check logs and diagnostic bundles to detect leaked credentials.
- Check access permissions and encryption of the image directory.
- Evaluate whether native libraries or SDKs keep key material in memory.

Do not run arbitrary scanning tools on production images if the tool might create temporary copies, dump plaintext, or write secrets to output. The scanner also needs to be protected as a tool handling sensitive data.

When using canary secrets, use only dummy values in a test environment. Do not put production credentials into tests or examples.

### Do not include secrets in reports

When detecting strings resembling tokens or passwords, the report should only contain:

- Data type.
- Related location or component.
- Secret identifier or safely processed hash.
- Severity level.
- Remediation guidance.

Do not copy verbatim secret values into tickets, logs, or inspection reports.

## 14. Protecting backups and checkpoint image lifecycle

Checkpoint images are often treated as reusable artifacts. Therefore, explicit lifecycle management is needed:

~~~text
Create checkpoint
      |
      v
Encrypt and write to protected storage
      |
      v
Write metadata / audit
      |
      v
Distribute over secure channel
      |
      v
Verify image and restore permissions
      |
      v
Restore in authorized workload
      |
      v
Retain image per retention policy
      |
      v
Delete expired images, copies, and backups
~~~

Controls that should be in place:

- Encryption at rest and in transit.
- Access permissions based on roles and workload identity.
- Audit logs for read, copy, download, restore, and delete.
- Integrity checks or artifact signatures if supported by the platform.
- Clear retention policy.
- Deletion of copies in caches and staging.
- Backups protected at the same classification level.
- Prohibition of sharing over unmanaged channels.

If an image is automatically backed up by volume snapshots or backup agents, those copies need to be included in the retention period. Deleting the original file does not necessarily delete snapshots or backups.

## 15. Controlling the restore environment

Do not restore a production checkpoint into an untrusted environment merely for a quick check. Upon restore, sensitive data may reappear in the memory of the new process.

Before restoring, verify:

- Workload identity is correct.
- Node and namespace belong to an authorized environment.
- Secret manager/KMS policy allows this workload access.
- The checkpoint image is authenticated and unaltered.
- Network policy restricts outbound connections.
- Logs, tracing, and diagnostic endpoints are protected.
- Debuggers, heap dumps, and process inspection are restricted to authorized personnel.
- The readiness gate keeps traffic closed until checks are complete.

If an image is copied to staging, consider using dummy data and staging credentials. A production image can carry production secrets even when the external configuration of the new environment is staging.

## 16. Common mistakes

### Thinking that secrets in environment variables do not enter the image

After reading the environment, the application may hold secrets in Strings, configuration beans, or clients. The process environment also needs to be considered in the snapshot model.

Remedy: inventory both loading sources and objects holding values; protect the image as sensitive data.

### Assigning null and assuming the secret has been erased

Assigning null only drops the reference. It does not overwrite String contents or all copies.

Remedy: reduce copies, use mutable buffers when the API supports them, clear best-effort, and avoid holding secrets long-term. Do not claim absolute zeroization without guarantees from the provider/runtime.

### Closing the HTTP client while the token remains on the heap

close() releases client resources according to its implementation, but the token may still remain in configuration objects, header caches, or other Strings.

Remedy: identify where tokens are held, limit lifetime, clear temporary data, and obtain new credentials after restore.

### Credentials expire while the image sits idle

Restore may use an expired token or a rotated password.

Remedy: re-acquire secrets after restore, check version/expiry, and open traffic only when authentication succeeds.

### Deleting secrets in beforeCheckpoint when the checkpoint is aborted

The original process may continue, yet the credentials have been deleted. afterRestore() does not run in this branch.

Remedy: when calling Core.checkpointRestore(), catch CheckpointException and restore secrets/clients; if using external jcmd, have an independent recovery path or avoid irreversible cleanup steps.

### Encrypting the image while leaving the key inside the image

Anyone reading the image can obtain both the data and the decryption key.

Remedy: keep keys outside the image in an independent KMS/HSM or secret manager.

### Debug or heap dumps exposing secrets

Diagnostic artifacts can contain the same sensitive data as a checkpoint image.

Remedy: restrict permissions, redact logs, protect dumps, and apply retention/deletion similar to images.

## 17. Implementation procedure

### Before checkpoint

1. Inventory secrets, PII, and sensitive data across the heap, stack, buffers, and native memory.
2. Identify objects, caches, ThreadLocals, and clients holding credentials.
3. Stop accepting new requests and drain in-flight work.
4. Clear unnecessary request contexts, temporary sessions, and buffers.
5. Close clients or connections holding old sessions according to the designed lifecycle.
6. Overwrite mutable buffers that can be safely cleared.
7. Ensure credentials needed after restore can be re-issued from an independent source.
8. Do not perform irreversible cleanup without a recovery path if the checkpoint is aborted.
9. Create the image in protected storage.

### Protecting the image

1. Classify the image according to the highest sensitivity level of process memory data.
2. Encrypt at rest and in transit according to platform capabilities.
3. Keep encryption keys outside the image.
4. Restrict read, copy, download, and restore permissions.
5. Audit all access and operations.
6. Protect backups, caches, staging, and temporary copies.
7. Apply a retention policy and delete expired copies.

### After restore

1. Keep the request gate and workers in a state of not accepting work yet.
2. Authenticate the workload identity.
3. Obtain new credentials/tokens from the secret manager or KMS.
4. Recreate necessary HTTP clients, JDBC pools, and TLS sessions.
5. Check expiry, version, and access permissions.
6. Clear temporary secret buffers after creating clients.
7. Verify readiness before opening traffic.

### When the checkpoint is aborted

If the application calls Core.checkpointRestore(), catch CheckpointException and recover clients or credentials that were released in beforeCheckpoint(). If recovery fails, keep the application not-ready.

If the checkpoint is requested externally using jcmd, the application flow does not catch exceptions via API. Callback design and operational procedures must ensure the original process can recover; do not assume afterRestore() will run when a checkpoint is aborted.

## 18. Principles to remember

- Checkpoint images can contain data in the heap, stack, buffers, and native memory.
- Environment variables or secret files do not prevent loaded values from appearing in memory.
- Inventory passwords, tokens, key material, sessions, PII, request payloads, and caches.
- String is immutable; assigning null does not erase its contents.
- Overwriting char[] or byte[] is a best-effort measure and does not guarantee erasing all copies.
- Do not write secrets into logs, traces, URLs, command lines, or diagnostic output.
- Closing a client does not mean all credentials on the heap have been zeroized.
- Re-acquire credentials after restore from a secret manager, workload identity, KMS, or HSM when possible.
- Grant image access permissions using least privilege and encrypt copies, backups, and staging artifacts.
- Keep encryption keys outside the checkpoint image.
- Rotate or revoke credentials if an image may have been exposed.
- Do not restore production images into less trusted environments.
- Distinguish an aborted checkpoint from a successful restore; afterRestore() is not a rollback callback.
- Open traffic only after credentials and dependencies have been re-verified.

A checkpoint image is a record of process state and can carry secrets that the application previously loaded into memory. By inventorying secret sources, reducing data present at checkpoint time, protecting all image copies, and re-issuing credentials after restore, systems can retain fast startup benefits while keeping the risk of exposing sensitive information under control.
