# Expired or Rotated Database Credentials

In the CRaC lifecycle, a Java application can be checkpointed while still retaining database configuration, `DataSource` objects, connection pools, and authentication credentials in the heap. While the process is in the checkpointed state, the database password may be changed, authentication tokens may expire, credentials may be revoked, or client certificates may be replaced.

Upon restore, the JVM resumes from the saved state. Fields and configuration objects in memory do not automatically update according to the secret store. If the application continues to use old credentials to create new connections, the database may reject authentication. If a connection pool reuses an old session, behavior also depends on the database and rotation policy: some systems only affect new logins, while others may revoke or terminate existing sessions.

A CRaC application therefore needs to treat credentials as time-limited and mutable data. Before checkpoint, the application brings the connection pool to a safe state. After restore, the application reads the current credentials from the secret management source, creates a new pool/client, validates the connection, and only then allows receiving traffic.

## 1. Why can credentials become invalid after restore?

Credentials are typically loaded at application startup and held across multiple components:

- The `DataSource` or connection pool holds the username/password used when opening new connections.
- The JDBC driver or database library holds authentication configuration and session state.
- The application holds passwords, access tokens, refresh tokens, or credential objects in fields/caches.
- Secret SDKs may cache secrets by version or their own time-to-live.
- Client certificates and private keys may be loaded into a keystore or TLS context.

A checkpoint saves the process state at a point in time. Suppose the application is checkpointed at 09:00 with password version `v12`. At 09:20, the security system rotates to `v13` and revokes `v12`. When restored at 09:30, objects in the heap may still contain password `v12`, even though the secret store already returns `v13` for new workloads.

```text
09:00  JVM is running
       Credential v12 is loaded into DataSource/pool
             |
             v
       Create checkpoint
             |
             v
09:20  Database/secret store rotates to v13
       v12 may be revoked
             |
             v
09:30  Restore from old image
       Heap still contains v12 state
             |
             v
       Application must read v13 and create a new pool
```

The longer the checkpoint duration, the higher the likelihood that credentials have changed. Even when the checkpoint duration is short, a token with a TTL of a few minutes can still expire while the process is paused.

## 2. Types of credentials and their lifecycles

Not all authentication credentials are static passwords. It is necessary to identify the credential type to choose the appropriate refresh approach.

| Credential type | Characteristics | Action required after restore |
| --- | --- | --- |
| Username/password | May be rotated by an administrator or secret manager | Read the current version and reconfigure the pool before opening new connections. |
| Database access token | May expire after a short duration, sometimes bound to an audience or scope | Request a new token; check `expiresAt` and do not reuse the old token just because the object is still in the heap. |
| Cloud/IAM authentication token | May be signed or issued per connection, with a short TTL | Generate a new token when the pool opens a connection; avoid caching tokens beyond their expiration. |
| Client certificate/private key | Certificates have an expiration date and may be replaced or revoked | Load the new certificate/key and rebuild the TLS context or client if the library does not support safe reloading. |
| Trust store/CA bundle | CAs may be added, replaced, or removed | Read the new trust material and recreate the TLS context to authenticate the server under the current policy. |
| Credentials provided by a secret file | File contents may be updated by the deployment system | Re-read the file after restore; do not use the version parsed into objects before checkpoint. |

The application needs to know where credentials come from, what version they have, when they expire, and what refresh mechanism is supported. You should not assume every credential can be refreshed by replacing a password string in an existing `DataSource` object.

## 3. Distinguishing credentials in the heap from credentials at the source

The secret manager or token-issuing system is the source of truth. Objects in the heap are only copies read at a specific point in time.

For example, a bean might hold a password at startup:

```java
public final class DatabaseSettings {
    private final String username;
    private final String password;

    public DatabaseSettings(String username, String password) {
        this.username = username;
        this.password = password;
    }
}
```

If this bean is restored from a checkpoint, its fields do not automatically change when the external password has been rotated. Similarly, reading environment variables after restore usually still returns the environment values that the process received at launch; restore does not start a new process to pick up a new environment.

If the deployment updates secrets via a mounted file, the file contents must be re-read after restore and you must understand how the volume/mount updates data. You should not hold parsed contents in a singleton and assume that changing the file will automatically update the object.

A clear design should separate three layers:

- **Secret provider:** retrieves current credentials from the secret manager, IAM provider, or managed file.
- **Credential snapshot:** holds the value, version, and expiration time of the credentials retrieved at a point in time.
- **Database client/pool:** uses the snapshot to open connections. When credentials change, the client/pool is replaced according to the library's capabilities.

Do not store temporary IPs or endpoints together with credentials if they have independent lifecycles. Database endpoints can change separately; they need to be refreshed according to the corresponding network and service discovery policies.

## 4. Handling the connection pool before checkpoint

A connection pool may hold many connections already authenticated with old credentials. After a checkpoint period, these connections may be closed by the database, timed out by a firewall, or have their sessions revoked. The pool may also hold the old password to open additional connections when needed.

A preparation procedure typically includes:

1. Transitioning the application or database client to the `QUIESCING` state, preventing new work from using the pool.
2. Waiting for in-flight transactions/requests to complete within a bounded deadline.
3. Handling borrowed connections according to the pool and application policy.
4. Closing the pool or releasing sockets using the API supported by the library before checkpoint.
5. Retaining the factory/provider and logical configuration needed to create a new pool after restore.

You should not simply call `Connection.close()` on a pool-managed connection if that only returns the connection to the pool. You must use the proper pool/client close API. Nor should you assume a `close()`d pool can be `start()`ed again; many implementations require creating a new instance.

Closing the pool before checkpoint does not make all copies of the password disappear from the heap. Credentials may still reside in configuration objects, immutable strings, logs, or other caches. You should limit the number of places holding secrets and protect the checkpoint as sensitive data.

## 5. Reading current credentials after restore

In `afterRestore`, a Resource or lifecycle coordinator can perform the following steps:

1. Connect to the secret manager or read the current secret source.
2. Fetch the latest credential version for the application's identity.
3. Verify that the credential has not expired and has enough remaining lifetime for opening the pool.
4. Create a new pool/client from the fetched credential.
5. Open a test connection and perform an appropriate health check.
6. Only publish the new pool and open traffic after validation succeeds.

Do not call the secret manager while holding an application lock. Reading secrets may require DNS, a TLS handshake, or network I/O. Use timeouts and bounded retry/backoff, and ensure the callback has an overall deadline.

If the secret provider needs an HTTP client or another network Resource to connect, do not rely on implicit callback ordering between `Resource`s. Have the secret provider self-recover the connections it needs, or orchestrate the refresh and pool creation in a lifecycle coordinator with an explicit order.

## 6. Example of managing a DataSource with a Resource

The example below uses application-defined abstractions `SecretProvider`, `DatabasePoolFactory`, and `ManagedDatabasePool`. This approach avoids assuming that all pool libraries share the same API for replacing credentials or restarting after being closed.

```java
import org.crac.Context;
import org.crac.Resource;

import java.time.Instant;
import java.util.concurrent.atomic.AtomicReference;

public final class DatabaseResource implements Resource {
    private final SecretProvider secretProvider;
    private final DatabasePoolFactory poolFactory;
    private final AtomicReference<ManagedDatabasePool> currentPool =
            new AtomicReference<>();

    public DatabaseResource(
            SecretProvider secretProvider,
            DatabasePoolFactory poolFactory) {
        this.secretProvider = secretProvider;
        this.poolFactory = poolFactory;
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        stopAcceptingDatabaseWork();
        drainTransactionsWithTimeout();

        ManagedDatabasePool oldPool = currentPool.getAndSet(null);
        if (oldPool != null) {
            oldPool.close();
        }
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        DatabaseCredentials credentials = secretProvider.fetchCurrent();

        if (!credentials.expiresAt().isAfter(Instant.now().plusSeconds(30))) {
            throw new IllegalStateException("Database credential expires too soon");
        }

        ManagedDatabasePool candidate = poolFactory.create(credentials);
        try {
            candidate.validateConnection();
            currentPool.set(candidate);
            resumeAcceptingDatabaseWork();
        } catch (Exception e) {
            currentPool.compareAndSet(candidate, null);
            candidate.close();
            throw e;
        }
    }

    private void stopAcceptingDatabaseWork() { /* application-specific */ }
    private void drainTransactionsWithTimeout() { /* bounded wait */ }
    private void resumeAcceptingDatabaseWork() { /* application-specific */ }
}
```

The interfaces are illustrated at a conceptual level:

```java
import java.time.Instant;

public interface SecretProvider {
    DatabaseCredentials fetchCurrent() throws Exception;
}

public interface DatabasePoolFactory {
    ManagedDatabasePool create(DatabaseCredentials credentials) throws Exception;
}

public interface ManagedDatabasePool extends AutoCloseable {
    void validateConnection() throws Exception;
    @Override
    void close();
}

public record DatabaseCredentials(
        String username,
        char[] password,
        String version,
        Instant expiresAt) {}
```

The types above are application abstractions, not built-in CRaC classes. In a real implementation, `ManagedDatabasePool` can wrap HikariCP or another pool; `SecretProvider` can call Vault, a cloud secret manager, or read a secret file.

The code snippet focuses on the lifecycle. A production implementation needs to add a timeout for `drainTransactionsWithTimeout`, an overall deadline for secret retrieval and connection validation, synchronized pool publication, credential cleanup handling, and readiness state management. Do not open traffic just because `poolFactory.create()` returns; you must confirm that connections actually work.

If the callback has already closed the pool but another Resource or a subsequent dump step causes the checkpoint attempt to be aborted, the application still needs a recovery path for the original process if it continues running. Do not rely on `afterRestore` as a rollback callback for an aborted checkpoint; coordinate preparation and rollback in the application's lifecycle coordinator, or ensure the deployment does not reopen traffic until the pool is recreated and validated successfully.

## 7. Replacing the pool safely and avoiding old credentials

Once the new pool has been created and validated, the application needs to shift traffic to the new pool consistently. Do not let some requests continue using the old pool while the new pool is already published, unless the design explicitly supports an overlap phase.

A safe replacement strategy:

1. Block new requests from using the database and drain in-flight requests.
2. Create a new pool from the new credentials.
3. Validate the connection and run a side-effect-free health check query.
4. Swap the current reference to the new pool in a short synchronized operation.
5. Close the old pool once no requests are using it.
6. Reopen traffic.

If the application holds the pool via `AtomicReference`, swapping the reference can be done atomically, but you still need a mechanism to prevent requests from acquiring the old pool right as it is being closed. You can use quiesce/drain or a provider with a lease/reference-count mechanism. An atomic swap alone does not solve the lifecycle of requests currently using the old pool.

If the new pool fails to connect, do not publish it and do not mark the application as ready. Keep the `NOT_READY` state, close the candidate pool, and retry according to the deadline/retry policy. Do not silently fall back to credentials known to be expired or revoked.

## 8. Rotation strategies on the database and secret manager side

The application cannot control the entire way the database applies rotation. The credential issuance workflow must be coordinated with deployment timing and database capabilities.

### Rotation with an overlap window

If the database supports multiple credentials or two users with equivalent permissions during the transition period, you can:

1. Create the new credential.
2. Update the secret store with the new version.
3. Let the application refresh and verify connectivity with the new credential.
4. Wait for instances to switch to the new version.
5. Revoke the old credential after confirming no workloads are using it.

An overlap window helps reduce the risk of downtime, but you must limit the duration and permissions of the old credential. Do not keep two credentials active indefinitely.

### Immediate rotation

If the old credential is revoked immediately, all new connections using that credential may fail. Depending on the database, already-authenticated sessions may continue or also be terminated. Read the database's policy and test before applying. After restore, always create a new pool from the current secret rather than relying on session state in the checkpoint image.

### Short-lived tokens or IAM authentication

With short-lived tokens, generate a token when a connection needs to be opened or refresh before the token expires. Avoid checkpointing a token and reusing it after restore without checking `expiresAt`. If the token is time-signed, account for clock skew and leave a safety margin.

### Certificate rotation

If the database uses mutual TLS, after restore you must load the current certificate/private key and rebuild the TLS context or client according to the library's API. If the CA/trust store changes, the client also needs to reload the trust material. Do not disable certificate verification to work around rotation errors.

## 9. Credential expiration while the application is still running

Credential refresh is not only needed for CRaC. A continuously running application can also hold a pool longer than the TTL of a token or password version. There should be a periodic or rotation-event-driven refresh mechanism:

- Track `expiresAt` or the secret version.
- Start refreshing before the expiration time with a safety margin.
- Create and validate the new pool/client before replacing the current pool if policy allows overlap.
- Handle refresh errors according to readiness state and retry policy.
- Monitor the number of connections using old credentials if the database/driver provides telemetry.

Do not wait for the next login to fail before discovering that a credential has expired. However, authentication errors still need to be handled as a signal for a controlled one-time refresh; avoid infinite retries with the same old secret.

## 10. Timeouts, retries, and errors when fetching secrets

The secret manager may be temporarily unreachable right after restore due to DNS, network, IAM endpoint, or service startup delays. Refreshing needs an overall deadline, connection/read timeouts, and bounded retry/backoff.

Classify errors before retrying:

| Error | Appropriate action |
| --- | --- |
| Timeout or transient network error when calling the secret manager | Retry with backoff and jitter within the deadline; recheck network and resolver. |
| Unauthorized/forbidden when reading the secret | Check workload identity, IAM role, policy, and access permissions; do not loop infinitely. |
| Secret version does not exist or is revoked | Refresh metadata/version and handle according to the rotation workflow; do not use the old secret as a fallback if it has been revoked. |
| Credential expired | Request a new token/credential from the issuer; do not retry the database with the same expired token. |
| Database rejects authentication | Refresh the credential once per policy, then retry with a limit and record the version used. |
| Database unreachable | Check DNS, routes, firewall, and health; distinguish network errors from authentication errors. |

If valid credentials cannot be obtained within the deadline, the callback should report an error and the application must not open readiness. Letting an instance run with an unauthenticated pool can cause mass request failures or create hard-to-control states.

## 11. Protecting credentials in the checkpoint image

A checkpoint can contain the application's heap and memory state. If passwords, access tokens, private keys, or credential objects are in the heap, the checkpoint image may contain that data even if the application closes the connection pool before creating the image.

Therefore:

- Store checkpoints on storage with appropriate access control and encryption.
- Restrict which users and services are allowed to read, copy, or download checkpoints.
- Set a retention policy and delete old images through a controlled process.
- Do not include checkpoints in public artifacts, container images, or logs.
- Minimize the number of places holding credentials in the heap and avoid unnecessary secret copying.
- Do not write passwords, tokens, private keys, or secret contents into logs/exceptions.
- Consider revoking old credentials after rotation so old checkpoint images cannot use revoked secrets.
- Do not treat using `char[]` instead of `String` as a guarantee that secrets are completely erased; libraries and drivers may make internal copies.

If restoring from old checkpoints must be supported, the design must ensure the application fetches new credentials from the authoritative source rather than depending on the secret snapshot residing in the image.

## 12. Common errors after restore

| Symptom | Possible cause | Investigation direction |
| --- | --- | --- |
| `password authentication failed` when opening a new connection | The pool or DataSource is using an old password | Check the secret version, rotation timing, and pool configuration created after restore. |
| Token is expired immediately after restore | The token was checkpointed when close to its TTL | Re-read the token from the issuer and check the safety margin against `expiresAt`. |
| Pool object exists but cannot acquire a connection | The pool holds old sessions/sockets or was closed before checkpoint | Create a new pool and check the pool's lifecycle state. |
| Some requests succeed, some requests fail | Requests are using a mix of old and new pools/credentials | Check pool swapping, requests holding leases, and closing of the old pool. |
| Secret manager returns an old secret | SDK/provider caching or a fixed pinned version | Check cache TTL, version selector, and the provider's invalidation/refresh mechanism. |
| Restore cannot reach the secret manager | DNS/network/IAM not ready or invalid identity | Check network, workload identity, permissions, and bounded retries. |
| TLS handshake fails | Certificate, private key, or trust store has been rotated | Reload TLS material and build a new client/context; check hostname and trust chain. |
| New credential is valid but the database still rejects it | Wrong username/database/role, permissions not granted, or rotation not yet synchronized | Check account, database, role grants, secret version, and rotation status. |

## 13. Testing credential rotation between checkpoint and restore

An integration test should accurately simulate secrets changing while the application is not running:

1. Create database user/credential version `v1` in the test environment.
2. Start the application and verify the connection pool can open connections using `v1`.
3. Create a checkpoint after the application has completed startup and necessary work.
4. While the application is in the checkpointed state, create or activate credential `v2` and update the secret store.
5. Revoke `v1` according to the test policy, if the scenario needs to test an immediate rotation case.
6. Restore the application in a compatible environment.
7. Verify `afterRestore` reads `v2`, creates a new pool, and validates the connection.
8. Send database requests and verify they use the new pool.
9. Verify no logs contain secrets and no requests are still using the old pool.

Additional scenarios should include:

- Token expires before restore.
- Secret manager is temporarily unreachable.
- Secret version is revoked or IAM permissions are changed.
- New pool is created successfully, but the health query fails.
- Database rotation with overlap and immediate rotation.
- Restore from an old checkpoint after the secret has changed across multiple versions.
- Credentials are reissued successfully, but the TLS certificate or CA has also changed.
- Checkpoint is aborted after the callback has closed the pool; verify the application has a safe recovery path before receiving traffic again.

Tests should verify both success and fail-closed behavior: if valid credentials cannot be obtained, the application stays in the `NOT_READY` state and does not serve requests requiring the database.

## 14. Observing and tracing rotation

To analyze incidents, record metadata instead of recording secrets:

- Secret identifier and version, without logging the secret value.
- Time the credential was fetched and expiration time.
- Checkpoint attempt id and restore attempt id.
- Time taken to fetch the secret, create the pool, open a connection, and run the health check.
- Retry count, error type, and backoff duration.
- Pool/client generation currently serving requests.
- Number of requests/connections still using the old pool generation during the swap.
- Readiness state before and after restore.

Useful metrics include refresh success/failure counts, authentication error counts, soon-to-expire token counts, reconnect duration, and the number of requests rejected while the application is not ready. Avoid putting sensitive usernames or identifiers that could expose internal structure into high-cardinality metric labels.

## 15. Operational checklist

- [ ] Know where credentials are issued from and their rotation/expiry mechanism.
- [ ] Do not treat passwords/tokens in the heap as the source of truth after restore.
- [ ] Do not depend on environment variables loaded at process start if secrets can change.
- [ ] Be able to re-read the current secret version after restore.
- [ ] Before checkpoint, stop accepting new work, drain transactions, and close the pool using the appropriate API.
- [ ] After restore, fetch new credentials and check `expiresAt`/version.
- [ ] Create a new pool/client instead of assuming the old pool can safely swap credentials.
- [ ] Validate the connection before publishing the new pool and opening traffic.
- [ ] Have timeouts, an overall deadline, retry/backoff, and clear authentication error handling.
- [ ] Do not fall back to expired or revoked credentials.
- [ ] Have an overlap rotation strategy or coordinated revocation based on database capabilities.
- [ ] Protect checkpoint images because they may contain secrets in the heap.
- [ ] Do not log passwords, tokens, private keys, or secrets.
- [ ] Test rotation occurring between checkpoint and restore.
- [ ] When refresh fails, keep the instance `NOT_READY` until valid credentials and connections are available.

## 16. Conclusion

Credentials can expire or be rotated while an application is in the checkpointed state. Restore recovers objects and configuration in the heap from the time the image was created; it does not automatically update passwords, tokens, certificates, or secret caches from external sources. An old connection pool may also hold sessions and credentials that are no longer valid.

Manage the connection pool through the CRaC lifecycle: stop and drain work before checkpoint, close the pool using the appropriate API, read current credentials after restore, create a new pool, and validate the connection before opening traffic. Combine timeouts, bounded retries, overlap rotation when feasible, and checkpoint image protection so the application continues connecting to the database safely when credentials change.
