# Tokens, Certificates, Nonces, and Security Data That Must Not Be Reused Across Replicas

CRaC can restore the same checkpoint into multiple processes or replicas. Each replica starts from an identical memory state image, so objects created before the checkpoint can appear with the same values across multiple replicas. This is especially sensitive for security data: access tokens, refresh tokens, private keys, session IDs, nonces, random number generators, counters, and anti-replay state.

If multiple replicas reuse the same token or the same nonce generation state, the system may lose the ability to distinguish identities, encounter conflicts during credential rotation, or violate cryptographic requirements. A nonce reused with the same encryption key, such as AES-GCM, can severely weaken security. A single-use refresh token may be used concurrently by multiple replicas, causing one copy to succeed while the others are rejected.

Therefore, a checkpoint used for cloning must be prepared as a shared initial state, while each replica's unique identity and security data must be freshly issued or verified after restore. Every replica must complete this step before receiving traffic or performing cryptographic operations.

## 1. Why Does Restoring Multiple Replicas Create Security Risks?

Suppose an application initializes several objects before the checkpoint:

~~~java
static final SecureRandom RANDOM = new SecureRandom();
static String accessToken;
static long nextRequestId = 1000;
static PrivateKey signingKey;
static byte[] lastNonce;
~~~

If the checkpoint is restored into multiple replicas, this Java state can be duplicated with the exact same values:

~~~text
Checkpoint at time T
   |
   +--------------------+--------------------+
   |                    |                    |
   v                    v                    v
Replica A            Replica B            Replica C
   |                    |                    |
   | accessToken=X      | accessToken=X      | accessToken=X
   | nextRequestId=1000 | nextRequestId=1000 | nextRequestId=1000
   | signingKey=K       | signingKey=K       | signingKey=K
   | RNG state=R        | RNG state=R        | RNG state=R
   |                    |                    |
   +--------------------+--------------------+
            Values that may be reused
~~~

This is a different issue from starting multiple independent processes. When each process starts on its own and obtains fresh entropy or credentials, they can have different states. When multiple processes are created from the same snapshot, you cannot assume that every object in the heap will automatically become independent.

Categories of data to consider:

- **Tokens and sessions:** access tokens, refresh tokens, session cookies, API tokens, OAuth state, CSRF tokens, and short-lived authentication credentials.
- **Cryptographic identities:** private keys, certificate identities, client certificates, signing keys, and key handles.
- **Nonces and random state:** AEAD nonces, IVs, challenges, salts with specific uniqueness requirements, SecureRandom state, and custom PRNGs.
- **Counters and IDs:** local sequences, request IDs, message sequence numbers, anti-replay counters, and generation numbers.
- **Anti-replay state:** used nonces, caches of received tokens, session IDs, and sequence windows.
- **Cached security data:** credentials, secrets, key material, policy snapshots, and access permissions.

Not every value is required to differ across replicas. A truststore containing public CA certificates can be shared. A public key or non-secret configuration can also be identical. What needs to be distinguished is intentionally shared data versus data representing each replica's individual identity, ownership, or cryptographic state.

## 2. Distinguishing Shareable Data from Data That Must Be Issued Individually

| Data | Can be shared across replicas? | Appropriate policy |
|---|---|---|
| Public CA certificates and trust bundles | Usually yes | Share per trust policy; update when the CA changes |
| Issuer's public key | Usually yes | Share for signature verification, with versioning and rotation |
| Non-secret configuration | Can be | Share if in the same environment and same revision |
| Access token tied to a workload/replica | Should not be shared when separate identity is needed | Issue a new token after restore for each replica |
| Refresh token with rotation or single-use semantics | No | Do not clone the token; use workload identity or a coordinated token-issuing mechanism |
| Per-replica private key | No | Generate or retrieve a separate key from KMS/HSM/identity provider |
| Client certificate identifying a replica | Should be separate | Issue a certificate with a distinct subject/SAN or workload identity |
| Nonce used with the same encryption key | Must not repeat per algorithm requirements | Issue nonces independently or ensure a non-repeating allocator |
| SecureRandom/PRNG state | Should not continue using verbatim state across copies | Create/reseed a separate random source after restore |
| Local ID counter | Unsafe if cloned with the same value | Use a centralized sequence, range lease, or ID with a unique node identity |
| Intentionally shared configuration secret | Can be, if policy permits | Restrict permissions, protect checkpoints, and apply controlled rotation |

A public certificate and its accompanying private key serve different roles. Public certificates are typically used by many clients to verify a CA or a service identity. A private key is proof of identity ownership and must be protected. If each replica needs to be identified independently, issue a separate private key and certificate for each replica.

Some systems intentionally share a single service identity across all replicas. That can be valid by design, but it reduces per-replica accountability, widens the blast radius if a key is compromised, and causes rotation/revocation to affect all replicas. You should not accidentally create a shared service identity simply because the private key happened to be inside the checkpoint.

## 3. Tokens: Do Not Clone Credentials with an Individual Lifecycle

Tokens can carry access rights to databases, APIs, message brokers, or internal services. If a token is stored in the heap at checkpoint time, multiple replicas may restore the exact same token string.

Risks depend on the token type:

- Access tokens may be valid in multiple places simultaneously, but the replicas will share a single identity and permission scope.
- Refresh tokens may be rotated upon use; two replicas using the same token can cause a race condition, invalidating the old token or causing one replica to lose the ability to refresh.
- Session tokens may be bound to an expired connection, client, or server-side session.
- Expiring tokens may expire while checkpointed; the String object in the heap still holds the value, but the server will no longer accept it.
- Tokens may contain claims for audience, subject, scope, or instance ID that are no longer appropriate for the new replica.

### Issuing Tokens After Restore

A common pattern is for each replica to authenticate using the deployment environment's workload identity, and then exchange that identity for a short-lived access token:

~~~text
Restore checkpoint
       |
       v
Replica receives its own workload identity
       |
       v
Authenticate with identity provider
       |
       v
Exchange for a new access token
       |
       v
Create client with the new token
       |
       v
Health check and readiness
       |
       v
Receive traffic
~~~

Workload identity can come from a service account, cloud identity, SPIFFE/SPIRE, or an equivalent platform identity mechanism. The key point is that each replica is identified by a distinct identity or issuance session, rather than relying on a token saved inside the checkpoint.

If the system requires refresh tokens, issue a separate token per replica or use a token broker service that manages rotation. Do not copy a refresh token with single-use/rotation semantics across multiple replicas.

### Tokens Must Have Appropriate Scope and Lifetime

Fresh tokens after restore must still follow least privilege:

- Grant only the required audience.
- Grant only the scopes and roles the replica needs.
- Use a short lifetime appropriate for the refresh capability.
- Attach a traceable subject or workload identity.
- Support revocation/rotation when the replica terminates or is suspected of compromise.
- Do not write tokens to logs, metric labels, exceptions, or manifests.

Do not use a token with broad administrative privileges just to simplify the restore step. If a function needs elevated privileges, use a separate token with an appropriate scope and lifetime.

## 4. Certificates, Private Keys, and TLS Identities

A TLS certificate includes public identity information and the CA's signature. The corresponding private key proves that the party presenting the certificate owns that identity.

If a checkpoint contains one replica's private key and is restored into multiple copies, the replicas may share the same private key. During mTLS connections or data signing, external systems cannot distinguish between the replicas based on that key.

Potential consequences include:

- Unable to revoke one replica's access without affecting the remaining replicas sharing the key.
- Logs/audits on the target system cannot identify which replica performed an action.
- Rotation can cause races among replicas using the same certificate.
- One compromised replica can expose the shared identity of the entire group.
- The key could be used on a host or workload that is no longer authorized.

### Creating a Unique TLS Identity After Restore

With a per-replica identity model:

1. The replica receives its identity from the orchestrator or workload identity provider.
2. Generate a new key pair in KMS/HSM or within an appropriate security boundary.
3. Submit a CSR or identity issuance request per the provider's protocol.
4. Receive a certificate with a distinct subject/SAN or SPIFFE ID.
5. Create a new TLS client/server context with the new key and certificate.
6. Open connections only after checking the chain, expiration, and trust policy.
7. When the replica terminates, revoke the certificate or let it expire according to policy.

If using a KMS/HSM, prefer non-exportable private keys. The checkpoint may retain a handle or representative object, but that handle still needs to be verified after restore; the session to the KMS/HSM may need to be recreated. Do not treat a Java object representing a key as proof that permission to use the key is still valid.

### What Can Be Shared

Public CA certificates, trust anchors, and public keys used for signature verification can usually be shared across replicas. They are not secrets. However, the truststore still requires versioning, integrity checks, and controlled rotation.

Do not share CA signing keys or root private keys inside an application checkpoint. These keys should be kept in a KMS/HSM or dedicated key management system with strictly restricted access.

## 5. Nonces and Non-Repetition Requirements in Cryptography

A nonce is a value used once or required to be unique within a specific scope of a cryptographic protocol. Depending on the algorithm, a nonce may not need to be secret, but the non-repetition requirement is mandatory.

For example, with AES-GCM, reusing the same nonce with the same key across multiple encryptions can leak information and break the encryption mode's authentication guarantees. Exact safety rules must be determined per algorithm and library, but the core principle is:

**If the algorithm requires unique nonces under the same key, all replicas sharing that key must coordinate so they never generate duplicate nonces.**

Simply creating an AtomicLong in the heap is insufficient if all replicas are restored from the same value. Likewise, using a timestamp or PID as a nonce does not provide a uniqueness guarantee and is hard to control when replicas start concurrently.

### Three Common Strategies

**Use a separate key for each replica.** Each replica receives its own encryption key, so the scope of nonce uniqueness is isolated per key. Non-repeating nonces are still needed within each replica/key, and key/nonce pairs must not be reused when a replica re-initializes.

**Use a centralized nonce allocator or range lease.** If multiple replicas must share a key, allocate non-overlapping nonce ranges from an external durable source. Each replica receives a unique range or prefix after restore. Counters and leases must not be stored solely in the checkpoint's heap.

**Use random nonces with a CSPRNG and volume limits.** A cryptographic random source can reduce collision probability, but collision probability must be evaluated based on nonce size and total encryptions under the same key. This approach does not solve a cloned PRNG state if replicas continue using the same generator state.

With AES-GCM, many libraries commonly use 96-bit nonces. This size does not mean you can arbitrarily generate unlimited random nonces under the same key. You must follow encryption count limits, collision probability bounds, and the guidelines of the cryptographic library/standard in use.

### Do Not Construct Nonces from Time

The following approaches are insufficient to guarantee uniqueness:

- System.currentTimeMillis() or Instant.now().
- System.nanoTime().
- PID or container hostname.
- AtomicLong restored along with the checkpoint.
- A UUID generated before the checkpoint and then copied to all replicas.
- A custom-written PRNG or one seeded with time.

Multiple components can be combined in a nonce format if the protocol specifies it clearly, but each component must have proven uniqueness and be managed across the key's lifecycle.

## 6. SecureRandom and PRNG State After Restore

SecureRandom provides cryptographic random numbers according to the selected provider. However, the SecureRandom object and internal provider state are runtime state. If an instance is created before the checkpoint and restored into multiple replicas, you should not assume each copy will automatically have an independent sequence of random numbers.

A risk-prone pattern:

~~~java
public final class NonceService {
    private static final SecureRandom RANDOM = new SecureRandom();

    public byte[] nextNonce() {
        byte[] nonce = new byte[12];
        RANDOM.nextBytes(nonce);
        return nonce;
    }
}
~~~

This static field may be saved in the process state. After multiple restores, do not rely on each replica automatically having a different generator state.

### Creating or Reseeding the Random Source After Restore

After restore, create a new SecureRandom instance from an organization-approved provider/entropy source, or call the provider's documented reseed mechanism. Using **setSeed(System.nanoTime())** is not a safe way to reseed: timestamps are not cryptographic entropy and can be identical across copies.

Example illustrating a Resource managing the generator:

~~~java
import java.security.SecureRandom;
import java.util.Arrays;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class NonceGenerator implements Resource {
    private volatile SecureRandom random = new SecureRandom();

    public NonceGenerator() {
        Core.getGlobalContext().register(this);
    }

    public byte[] nextGcmNonce() {
        SecureRandom source = random;
        if (source == null) {
            throw new IllegalStateException(
                    "Nonce generator is not ready");
        }

        byte[] nonce = new byte[12];
        source.nextBytes(nonce);
        return nonce;
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) {
        // The checkpoint coordinator must drain all cryptographic operations
        // before allowing the snapshot.
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) {
        SecureRandom fresh = new SecureRandom();
        byte[] warmup = new byte[32];
        fresh.nextBytes(warmup);
        Arrays.fill(warmup, (byte) 0);
        random = fresh;
    }
}
~~~

The example replaces the generator before the application is allowed to perform encryption after restore. The warmup snippet only initializes the provider's operation; it is not an independent proof that entropy is strong enough. Select a platform-approved provider and entropy source, check the provider's documentation on reseeding, and test on the exact JDK/CRaC runtime.

Do not allow requests or cryptographic tasks to run before afterRestore completes. If multiple independent Resources may be invoked in an unspecified order, use a readiness gate or coordinator to ensure NonceGenerator is ready before opening cryptographic processing paths.

If the system uses a durable nonce counter or range lease, afterRestore must request a new range from the external source. Replacing SecureRandom alone does not substitute for a centralized nonce allocation mechanism when multiple replicas share a key and the protocol requires absolute uniqueness.

## 7. Counters, Request IDs, and Anti-Replay State

Values such as AtomicLong, sequence numbers, message offsets, or replay caches can also be cloned from the checkpoint.

For example, two replicas restore the same counter 5000 and then both generate the next ID. If IDs must be globally unique, both may emit ID 5001. A similar situation can roll back an anti-replay sequence or cause two replicas to accept the same message.

Do not use an in-heap counter as the sole source for global IDs when the process can be cloned.

Common options:

- Atomic database sequence or ID service.
- Durable range allocator where each replica receives a new range after restore.
- IDs containing a unique node/replica identity assigned by the orchestrator or coordinator.
- UUID/ULID or random ID formats following an evaluated standard, with a CSPRNG properly initialized after restore.
- Replay protection stored in a durable shared store or central authentication service.

For anti-replay, differing IDs alone are not enough. The server needs to store or check nonces, timestamps, sequences, or token IDs under a policy with a clear expiration and scope. If the replay cache resides only in the heap and gets cloned, multiple replicas may start with the same anti-replay window and make inconsistent decisions.

## 8. CRaC Lifecycle for Security Data

A security Resource can participate in the preparation and recovery workflow:

~~~text
Before checkpoint
    |
    v
Stop accepting requests and drain cryptographic operations
    |
    v
Close clients / release key handles
    |
    v
Remove temporary tokens, nonce cache, and identity from snapshot
    |
    v
Create checkpoint
    |
    v
Restore into a new replica
    |
    v
Receive unique identity from platform
    |
    v
Issue new token / certificate / key handle
    |
    v
Initialize new SecureRandom or nonce allocator
    |
    v
Verify permissions, expiration, and dependencies
    |
    v
Open readiness
~~~

Not every secret needs to be cleared before checkpoint. Some configuration secrets may be intentionally shared and needed at startup. However, short-lived tokens, sessions, per-replica private keys, nonces, and PRNG state must be evaluated against cloning risks.

If you choose to clear tokens or key material before checkpoint, there must be a recovery path in case the checkpoint is aborted and the original process continues running. A beforeCheckpoint callback does not guarantee it will always be followed by afterRestore. The checkpoint coordinator must detect checkpoint failures, request credential re-issuance for the current process, and only open admission once recovery completes.

### Example Resource Managing Per-Replica Security Context

The example below uses application-defined interfaces. IdentityIssuer is responsible for obtaining a unique identity from the platform, issuing a new token/key/certificate, and creating a security context for the current replica.

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ReplicaSecurityResource implements Resource {
    public interface WorkGate {
        void stopAdmissionAndDrain() throws Exception;
        void resumeAdmission() throws Exception;
    }

    public interface IdentityIssuer {
        ReplicaSecurityContext issueForCurrentReplica()
                throws Exception;
    }

    public interface ReplicaSecurityContext extends AutoCloseable {
        void verify() throws Exception;
        @Override
        void close() throws Exception;
    }

    private final WorkGate gate;
    private final IdentityIssuer issuer;
    private volatile ReplicaSecurityContext securityContext;

    public ReplicaSecurityResource(
            WorkGate gate,
            IdentityIssuer issuer) {
        this.gate = gate;
        this.issuer = issuer;
        Core.getGlobalContext().register(this);
    }

    public ReplicaSecurityContext current() {
        ReplicaSecurityContext current = securityContext;
        if (current == null) {
            throw new IllegalStateException(
                    "Replica security context is not ready");
        }
        return current;
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        gate.stopAdmissionAndDrain();

        if (securityContext != null) {
            securityContext.close();
            securityContext = null;
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        ReplicaSecurityContext fresh =
                issuer.issueForCurrentReplica();
        try {
            fresh.verify();
            securityContext = fresh;
            gate.resumeAdmission();
        } catch (Exception failure) {
            fresh.close();
            throw failure;
        }
    }

    // Called by the checkpoint coordinator if the checkpoint is aborted and
    // the current process continues running instead of being restored.
    public synchronized void recoverAfterAbortedCheckpoint()
            throws Exception {
        if (securityContext == null) {
            ReplicaSecurityContext fresh =
                    issuer.issueForCurrentReplica();
            fresh.verify();
            securityContext = fresh;
        }
        gate.resumeAdmission();
    }
}
~~~

This is an illustrative skeleton, not a built-in IdentityIssuer in CRaC. An actual implementation must:

- Obtain the current replica's unique workload identity.
- Request a new token and certificate from the issuer.
- Create or open a separate key handle, preferring KMS/HSM when appropriate.
- Verify audience, scope, subject, expiration, and trust chain.
- Close old clients and release old handles per the library's contract.
- Do not log secret values or private keys.
- Open admission only after the entire security context is ready.

If a recovery step fails, do not publish a half-ready context. The application must keep readiness set to false and either retry or fall back to cold start per operational policy.

## 9. Assigning a Unique Identity to Each Replica

Replica identity needs to come from a source capable of distinguishing individual instances. You can use:

- Pod/container UID or instance ID assigned by the orchestrator.
- Cloud provider workload identity.
- Service account with per-workload identity.
- SPIFFE ID or equivalent workload identity.
- An identity broker that issues IDs and credentials when a replica registers.

Do not rely solely on hostname, PID, or timestamp to construct an identity. Those values can collide, change, or be reused. If using an orchestrator-assigned replica ID, verify its uniqueness within the scope required by the security system.

An identity issuance workflow might be:

1. The replica restores and remains in a not-ready state.
2. Read the workload identity from the protected environment.
3. Authenticate with the identity provider.
4. Receive a new identity/lease for the replica.
5. Issue an access token and certificate bound to that identity.
6. Create new clients and verify permissions.
7. Publish the replica identity for telemetry/audit without exposing secrets.

If the orchestrator can start multiple replicas concurrently from the same checkpoint, the identity provider must support parallel issuance and distinguish each instance. Do not use a static credential file baked into the image as a unique identity for all replicas.

## 10. Handling Token Rotation and Concurrent Refresh

A common mistake is multiple replicas restoring the same refresh token issued before the checkpoint. If the issuer uses refresh token rotation, the first replica to refresh can receive a new token and invalidate the old one. The second replica using the old token may be rejected or flagged as anomalous behavior.

Solutions:

- Issue separate refresh credentials for each replica.
- Use workload identity so each replica exchanges it for a fresh access token independently.
- Use a token broker that manages refreshes centrally and issues separate access tokens.
- Use a distributed lock/lease if a rotating credential must be shared; however, lease expiration and ambiguous refresh outcomes must be handled.
- Do not include rotated tokens inside the checkpoint artifact.

Do not let all replicas refresh a shared token simultaneously without coordination. That can cause a thundering herd, race conditions, and a revocation cascade.

## 11. Protecting Checkpoint Artifacts Containing Security Data

Even when the application plans to replace tokens and keys after restore, the checkpoint image may still contain copies of pre-checkpoint data. The checkpoint can include the heap, static fields, buffers, object graphs, credential caches, and various runtime states.

Protect the checkpoint as a sensitive artifact:

- Encrypt at rest and in transit using organization-approved mechanisms.
- Restrict read, write, download, and copy permissions for the checkpoint.
- Grant restore permissions only to authenticated workloads and pipelines.
- Retain audit logs for creation, download, decryption, restore, and deletion of artifacts.
- Set retention periods and secure deletion procedures.
- Do not write secrets, tokens, private keys, or sensitive nonces into manifests, logs, or filenames.
- Do not push checkpoints to public artifact repositories.

Artifact encryption does not replace re-issuing identities after restore. If multiple replicas decrypt the same checkpoint, they can still receive the same old tokens or keys. Encryption only protects data at rest and in transit; uniqueness and freshness must be addressed in the application's lifecycle.

## 12. Testing Against Reuse Across Replicas

Testing needs to create multiple replicas from the same checkpoint, not just restore once and verify the application works.

Scenarios to test:

- Concurrently restore the same checkpoint into multiple replicas and verify each replica receives a different identity.
- Compare the subject/SAN or workload ID of each replica's certificate.
- Verify distinct private key handles or key IDs if policy requires per-replica keys.
- Verify access tokens have subject, audience, scope, and token ID matching each replica.
- Verify refresh tokens are not shared or do not race during rotation.
- Generate a representative number of nonces on each replica and check uniqueness within any shared key scope.
- If using separate keys, verify key IDs differ and nonces do not repeat within each key.
- Restore multiple times from the same checkpoint to detect repeated PRNG sequences or counters.
- Check that replay caches and anti-replay sequences do not roll back or get improperly duplicated.
- Make the secret provider or identity provider unavailable to verify that the replica does not open readiness.
- Check that checkpoint images, logs, and manifests do not leak secrets.
- Test a checkpoint aborted after beforeCheckpoint and confirm the original process can re-acquire credentials before receiving traffic.

Do not print nonces, tokens, or keys to logs for comparison. Use fingerprints, key IDs, non-sensitive token metadata, or issuer-side verification results. For nonces, you can test for collisions in a test environment and inspect the allocation policy; a finite test does not absolutely prove uniqueness for all runs.

## 13. Common Misconceptions

**"Each restored container automatically has a different SecureRandom state."**

Do not assume that. The object and generator state may reside in the checkpoint. Create/reseed a separate random source after restore and verify the actual provider/runtime.

**"A UUID or timestamp is always sufficient to create a unique nonce."**

Not every UUID or timestamp meets the algorithm's requirements. Use a nonce format and allocation source designed for the specific cryptographic protocol.

**"The token is still valid, so it can be shared."**

A token may be valid in terms of expiration while still carrying a shared identity, being bound to a single session, or having rotation semantics. Issue separate credentials if replicas need separate identities.

**"Only the private key needs to differ; refresh tokens can be shared."**

Refresh tokens may be single-use or rotating. Multiple replicas using the same token can invalidate each other's credentials. You must understand the issuer's semantics.

**"Certificates are public data, so everything can be copied."**

Public certificates can be shared, but the corresponding private key is secret. If the certificate identifies a replica, issue a separate identity and key for each replica.

**"Replacing the token after restore is enough."**

Nonce allocators, PRNG state, request counters, replay caches, key handles, and certificates can also be cloned. All security data and anti-replay state must be examined.

**"Encrypting the checkpoint guarantees replicas are independent."**

Encryption protects the artifact at rest/in transit. It does not make objects in the heap differ after they are decrypted and restored from the same checkpoint.

**"You can clear credentials in beforeCheckpoint without any extra handling."**

If the checkpoint fails and the current process continues, the cleared credentials may need to be re-issued. There must be a recovery path for a checkpoint abort.

## 14. Recommended Implementation Workflow

A practical workflow can be executed in order:

1. Inventory all tokens, secrets, keys, certificates, nonce generators, counters, and replay state that may reside in the heap.
2. Classify which data is intentionally shared and which must be unique per replica.
3. Design a workload identity or identity broker to issue unique identities after restore.
4. Issue short-lived tokens and separate certificates/private keys per policy; keep root keys in KMS/HSM.
5. Use an approved SecureRandom provider and re-initialize/reseed it after restore.
6. If sharing an encryption key, implement a non-cloned nonce allocator such as a range lease or durable allocation service.
7. Stop admission and drain all cryptographic operations before checkpoint.
8. Remove or invalidate per-replica credentials and state that must be re-issued in the snapshot.
9. After restore, create a new security context, verify keys/tokens/certificates, and restart clients.
10. Open readiness only when identity and security resources are ready.
11. Test multiple concurrent replicas from the same checkpoint as well as rotation/failure scenarios.
12. Protect checkpoint artifacts, manifests, logs, and the restore workflow.

## 15. Conclusion

When a checkpoint is cloned into multiple replicas, any security data residing in the heap risks being duplicated with identical values. Tokens, refresh tokens, private keys, certificate identities, nonce generators, counters, and replay state must be evaluated for uniqueness, freshness, and identity requirements.

Issue separate identities and credentials after restore, create or open separate key handles, re-initialize random sources from approved entropy, and use a nonce allocator guaranteed not to repeat within the key scope. Public trust material can be shared when appropriate, but private keys and individual credentials should not be unintentionally cloned. Open traffic only after each replica has completed security recovery; at the same time, protect the checkpoint image because it may contain copies of secrets prior to being refreshed.
