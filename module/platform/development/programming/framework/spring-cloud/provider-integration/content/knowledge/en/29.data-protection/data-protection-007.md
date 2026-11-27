# Key Rotation, Access Revocation, and Credential Exposure Response

Spring Boot applications routinely hold or rely on many types of credentials: workload identities, API keys, OAuth client secrets, refresh tokens, webhook secrets, certificates, signing keys, and data encryption keys. If any credential leaks, attackers can impersonate the workload, read data, sign forged requests, or decrypt stored data. Simply deleting a credential from a configuration file does not invalidate the old credential.

Safe management requires three interconnected capabilities:

- **Rotation:** replacing the current credential/key with a new version on schedule, with transition verification and defined retirement of the old version.
- **Revocation:** blocking a credential, token, session, or granted permission when it is no longer permitted.
- **Incident response:** detecting, scoping, isolating, eradicating root causes, recovering, and verifying after a credential is exposed or suspected of abuse.

Scheduled rotation reduces credential lifetimes, yet never substitutes for emergency handling. Once a secret is known to be exposed, prioritize containment and revocation; never wait for the next scheduled rotation. For data encryption keys, revoking/disabling too early can break decryption for live applications and backups. Always distinguish authentication credentials from KEKs/DEKs protecting data.

This lesson belongs to the **Data Protection** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module practices integrating Spring Boot with managed services from AWS, Azure, and Google Cloud via their corresponding Spring Cloud libraries. The focus of this lesson is building inventories, rotating identities and secrets, revoking access, handling compromises, preserving recoverability, and reviewing audits.

## 1. Learning Objectives and Running Scenario

After this lesson, you will be able to:

1. Distinguish among rotation, expiration, disabling, revocation, and destruction.
2. Build an inventory of credentials, certificates, signing keys, KEKs, and DEKs.
3. Design zero-downtime rotation using key IDs and overlap windows.
4. Use workload identities instead of long-lived access keys when supported by the platform.
5. Rotate API keys, OAuth client secrets, refresh tokens, webhook secrets, and TLS certificates.
6. Manage AWS IAM/STS/KMS, Azure Entra ID/Managed Identity/Key Vault, and Google IAM/Workload Identity/KMS.
7. Revoke active permissions and sessions scoped precisely to the impact radius.
8. Respond to credentials exposed in Git, CI/CD, logs, container images, or developer machines.
9. Build an incident response playbook covering containment, recovery, evidence, and post-incident review.
10. Test rotation, revocation, rollback, key versions, and backup decryption capability.

Scenario: **document-service** runs on Kubernetes, stores contract files in object storage, and encrypts DEKs with KMS. The service uses workload identity to call storage, OAuth client credentials to call a partner system, a webhook secret to verify callbacks, and certificates to protect internal connections. An old access key accidentally appears in CI logs; operations must determine the key's permissions, cut off access, rotate related credentials, and verify no unauthorized data access occurred.

~~~mermaid
flowchart TD
    A["Detect potentially exposed credential"] --> B["Identify type, owner, scope, and dependencies"]
    B --> C["Assess active abuse vs. potential exposure"]
    C --> D["Contain: revoke / disable / deny / isolate"]
    D --> E["Create new credential or key"]
    E --> F["Update workloads and verify"]
    F --> G["Retire old version on schedule"]
    G --> H["Review logs, access, data, and downstreams"]
    H --> I["Preserve evidence + improve guardrails"]
~~~

**There is no single universal revoke action across all key types.** Deactivating an IAM access key, revoking an OAuth refresh token, disabling a KMS key version, and deleting an application share grant have different semantics and blast radii.

## 2. Distinguishing Operations in the Credential Lifecycle

| Operation | Meaning | Example | Impact to understand |
| --- | --- | --- | --- |
| Create | Provision a new credential/key | Create a new client secret | Does not mean workloads are using it yet |
| Activate/enable | Permit a credential/key to be used | Enable an access key or KMS key version | Can unlock new permissions |
| Rotate | Transition to a new credential/key | Replace secret version A with B | Requires coordinating senders, receivers, and consumers |
| Expire | End validity based on time | OAuth access token expires | Old credential becomes invalid per policy |
| Disable | Temporarily block usage | Disable an IAM access key | Can be re-enabled if appropriate; data encrypted with the key may become unreadable |
| Revoke | Withdraw granted authority/delegation | Revoke a refresh token or application grant | May require server-side invalidation or policy enforcement |
| Delete | Remove the credential/key object | Delete an old IAM access key | Can forfeit recovery capability or audit metadata |
| Destroy/purge | Destroy key material or permanently delete | Purge a key after soft-delete window | Can render data permanently undecryptable |

### 2.1. Rotation is not revocation

Rotation is a controlled transition process. For example, create webhook secret B, configure the receiver to accept A and B, update the sender to use B, monitor traffic, and then remove A. During the overlap window, both secrets remain valid.

Revocation cuts off authority for a suspected compromised credential. If secret A leaked, leaving A active merely to wait for a planned cutover gives attackers extra time. Incident response may require revoking A immediately and accepting a controlled interruption.

### 2.2. Expiration does not replace revocation

An access token with `exp` in 15 minutes will expire automatically, yet an attacker can still use that token during those 15 minutes. If a token leaks, you need revocation/introspection/denylist mechanisms or session termination. With self-contained JWTs, a resource server might not know a token was revoked without additional state or checks.

### 2.3. Disabling and destroying encryption keys requires caution

Disabling a KMS key can break every application trying to decrypt data with that key. Destroying key material can make ciphertexts, snapshots, and backups permanently unrecoverable. Never treat a KMS key like an API key that can be deleted immediately after deploying a new one.

### 2.4. Credential rotation and key rotation differ

- Credential rotation replaces authentication secrets or identities.
- Signing-key rotation replaces keys that sign requests/tokens/certificates.
- KEK rotation replaces the key protecting DEKs.
- DEK rotation replaces the key encrypting payloads.
- Database password rotation replaces database connection credentials.
- Certificate rotation replaces certificates and possibly private keys/trust chains.

Each category needs its own inventory, dependency tracking, testing, and rollback plan.

## 3. Credential Inventory and Classification

You cannot rotate or revoke safely without knowing where credentials live and who uses them.

### 3.1. Credential inventory

Each record should capture fields such as:

| Attribute | Example |
| --- | --- |
| Credential ID | `payment-api-prod-v3` |
| Type | OAuth client secret |
| Owner | Payment Integration team |
| Consumer | `document-service` |
| Environment | Production |
| Provider/resource | Entra application / partner API |
| Scope | `invoice.write` |
| Created at | Issuance timestamp |
| Last rotated at | Most recent rotation timestamp |
| Expiry | Expiration timestamp |
| Secret location | Secret Manager/Key Vault/Secret Manager |
| Version/key ID | Resource/version identifier |
| Rotation method | Manual, automated, provider-managed |
| Revocation method | Revoke credential, disable key, policy deny |
| Dependencies | API gateway, workers, batch jobs |
| Audit | Logs and accountable owner |

Never record raw secrets or private keys in the inventory. Record references to the secret manager and version.

### 3.2. Classification by impact potential

| Type | Examples | Questions to evaluate |
| --- | --- | --- |
| Workload identity | IAM role, managed identity, service account | How tightly can principal/resource/actions be scoped? |
| Static API credential | API key, database password | Can it be replaced by a short-lived identity? |
| OAuth credential | Client secret, refresh token | Which tokens were issued and which audiences are affected? |
| Webhook signing secret | HMAC secret | Do sender and receiver support overlap? |
| Asymmetric signing key | RSA/ECDSA private key | Where were public keys/certificates distributed? |
| TLS certificate | Service certificate, CA | Which consumers trust the certificate/issuer? |
| Data encryption key | DEK/KEK | Which ciphertexts, envelopes, and backups depend on this key? |
| Session credential | Cookie, session ID | Which session stores or signing keys must be invalidated? |

### 3.3. Owners and dependency graphs

A single secret may be shared by multiple services, jobs, or environments. Before rotating, determine:

- The producer generating the credential.
- Consumers using the credential.
- The secret manager distributing versions.
- Whether runtimes load secrets only at startup or refresh periodically.
- How long connection pools/caches retain old credentials.
- Whether downstreams support two concurrent credentials.
- Whether logs/audits indicate which credential version is in use.
- Whether rollback can revert to the old version or if the old version must be revoked immediately.

During a credential compromise, this graph scopes the blast radius and identifies secondary credentials that may also have been exposed.

### 3.4. Prioritize eliminating long-lived secrets

Order of preference:

1. Workload identity or federated identity.
2. Short-lived access tokens/temporary credentials.
3. Secret manager provisioning and versioning secrets.
4. Static keys with TTLs, narrow scope, rotation, and auditing only when no alternative exists.

Never place long-lived cloud credentials in source code, Docker images, public Helm values, unprotected Terraform state, unrestricted CI variables, or committed `.env` files.

## 4. Zero-Downtime Rotation Workflow

### 4.1. Overlap model

A standard workflow:

~~~mermaid
sequenceDiagram
    participant Admin as Operator
    participant SM as Secret Manager
    participant App as Spring Boot
    participant Provider as External Provider
    Admin->>SM: Create secret version B
    SM-->>App: Publish reference/version B
    App->>Provider: Authenticate using B
    Provider-->>App: Success
    App->>Provider: Continue accepting A during overlap
    Admin->>Provider: Retire/revoke credential A
    Provider-->>App: A no longer valid
    App->>Provider: Verify B still works
~~~

Sequence:

1. Identify owner, consumers, expiry, scope, and revocation method.
2. Verify whether the provider supports multiple active credentials.
3. Create new version B.
4. Distribute B via secret manager or workload identity.
5. Update a single instance/canary first.
6. Verify new requests succeed using B.
7. Roll out B to all workloads and jobs.
8. Monitor authentication errors, remaining traffic on A, and downstreams.
9. Revoke A once the overlap window ends.
10. Verify A is rejected and B continues working.
11. Update inventory, audits, and rotation timestamps.

### 4.2. Overlap window

The overlap must be long enough to update every consumer without lingering unnecessarily. Account for:

- Deployment and restart cycles.
- Newly autoscaled instances.
- Scheduled batch jobs.
- Long-running workers/queue consumers.
- Secret caches and connection pools.
- Webhook/event retry windows.
- External clients unable to deploy simultaneously.

Never leave two secrets active indefinitely. Establish deadlines, alerts, and an owner for retiring the old key.

### 4.3. When is overlap impossible?

Some providers allow only one key or a strict key count limit. In that case:

- Schedule a maintenance window if needed.
- Prepare deployments/configs prior to cutover.
- Keep a rollback plan for the new credential if no compromise occurred.
- For compromises, prioritize immediate revocation; accept downtime if required to block attackers.
- If the provider allows minting a new credential without concurrent keys, use the provider-supported migration/bridge mechanism.

### 4.4. Automated vs. manual rotation

Automated rotation works well when the provider offers APIs and the secret manager can coordinate consumer updates. Automation does not eliminate verification:

- Was the new secret created with the right scope?
- Did consumers actually load the new version?
- Did connection pools reopen using the new credential?
- Was the old credential revoked?
- Are alerts triggered if rotation fails?
- Can we recover if the new secret fails?

Manual rotation requires checklists, change records, owners, timestamps, and verification evidence. Never treat a calendar reminder as proof that a credential was replaced.

## 5. Rotating API Keys, OAuth Secrets, and Session Tokens

### 5.1. API keys

API keys are bearer credentials. Good design includes:

- A public key ID for lookup, separate from the secret.
- High-entropy secret displayed only once.
- Secret hash stored in the database when only verification is needed.
- Explicit scope/resources/actions.
- Expiry and last-used timestamps.
- Quotas/rate limits.
- Owner and active/revoked state.
- Audits on creation, rotation, usage, and revocation.

When rotating, create a new key, update consumers, verify the new key, and revoke the old key. If a key leaks, revoke immediately and investigate requests made with that key.

### 5.2. OAuth client secrets

For the client credentials flow:

1. Create a new client secret/certificate at the authorization server.
2. Store the secret version in the secret manager.
3. Update the Spring Boot client registration.
4. Verify new tokens carry expected issuer, audience, scope, and expiry.
5. Shift traffic to the new credential.
6. Revoke the old client secret.
7. Monitor token issuance and resource access.

A new client secret affects only subsequent token requests. Previously issued access tokens may remain valid until `exp` unless the authorization server/resource server supports revocation/introspection.

### 5.3. Refresh tokens

Refresh tokens can mint new access tokens and require stricter protection than access tokens:

- Revoke the token or token family upon detecting compromise.
- Use refresh-token rotation and reuse detection when supported by the authorization server.
- Invalidate sessions per user/client.
- Never delete a token from browser/local storage and treat it as revoked.
- Verify server-side revocation and token family state.
- Assess whether access tokens minted from the exposed refresh token are still valid.

### 5.4. JWT signing keys

When rotating JWT signing keys:

1. Generate a new key pair and publish the public key/JWKS with a new key ID.
2. Verifiers must trust both old and new public keys during overlap.
3. Switch the issuer to sign new tokens with the new private key.
4. Confirm verifiers have fetched the updated JWKS.
5. Wait for older tokens to pass TTL or revoke them via supported mechanisms.
6. Remove the old public key once no valid tokens depend on it.

Do not delete the old public key the moment the issuer switches keys; existing access tokens may still be valid. If a private signing key leaks, switch signing keys immediately and evaluate tokens issued during the compromise window.

### 5.5. Webhook secrets

Webhook HMAC setups typically need current/previous secrets:

- A key ID header identifies the secret version.
- The receiver verifies against permitted key IDs.
- The sender switches to the new secret.
- Retain the old secret only long enough to cover retry windows.
- Revoke the old secret afterward.
- If a secret leaks, do not extend overlap for convenience; coordinate key change and block forged requests.
- Event IDs/inboxes remain necessary for replay protection; rotating secrets does not eliminate duplicate risks.

## 6. Certificate and TLS Private Key Rotation

### 6.1. Certificate lifecycle

Certificates carry a public certificate, private key, issuer/CA, SAN, validity period, and chain. Expiration provides a built-in end date, yet private key compromise requires early revocation/replacement.

- Monitor expiration dates and issuers.
- Verify SAN/hostnames.
- Distribute the new trust chain before cutover if the CA changes.
- Deploy the new private key to the secret/certificate store.
- Reload the application/proxy or perform a rolling restart as supported.
- Verify handshakes and mutual TLS from real consumers.
- Revoke the old certificate per CA/PKI policy when required.

### 6.2. Do not check expiration dates alone

A certificate may still be within its validity window while its private key is compromised. Upon compromise:

1. Generate a new key pair; never reuse the old private key.
2. Issue a new certificate.
3. Update server/client identities.
4. Update trust/revocation lists if applicable.
5. Revoke the old certificate at the CA or per corresponding policy.
6. Inspect connection logs and identify clients still presenting the old certificate.

CRL/OCSP and client revocation checking vary across TLS stacks. Never assume every client checks revocation identically; test actual behavior.

## 7. Managing AWS Credentials and KMS

### 7.1. IAM access keys and STS

Prefer IAM roles and temporary credentials for EC2, ECS, EKS, Lambda, or workload federation. Static IAM user access keys should be minimized.

If an access key must be rotated:

1. Create a new access key if quota allows.
2. Update secret stores and consumers.
3. Verify CloudTrail shows requests using the new key.
4. Deactivate the old key.
5. Monitor errors during the permitted rollback window.
6. Delete the old key after confirming zero consumers remain.

If a key leaks, deactivate immediately and investigate CloudTrail, IAM activity, and accessible resources. Do not merely delete the key from source repositories.

Temporary STS credentials are time-bounded and constrained by role session/policies. If session abuse is suspected, evaluate revoking active sessions or applying deny policies per AWS guidance; note this can impact multiple sessions of the role.

### 7.2. AWS Secrets Manager

Secrets Manager stores secrets and supports version stages like `AWSCURRENT`, `AWSPREVIOUS`, and `AWSPENDING` in rotation workflows.

- Create a new secret version.
- Test the new credential against the target system.
- Promote the current stage once verified.
- Consumers refresh secrets per cache policy.
- Revoke the old credential on the target system.
- Retain the old version only per retention and rollback policy.

Rotation Lambdas/automations must be idempotent. If a workflow reruns after a timeout, it must not spawn uncontrolled credentials or delete active ones.

### 7.3. AWS KMS key rotation

Distinguish between:

- Automatic rotation for symmetric customer managed KMS keys: KMS creates new key material while preserving the ability to decrypt older ciphertexts using the matching key material version.
- Manual rotation by creating a new KMS key: the key ARN/ID changes; applications and resources must switch to the new key.
- Re-encrypt/rewrap: must be executed separately to move data/DEKs onto a new key.
- Disabling a key: can break decryption for all data depending on that key.

Automatic rotation does not change the key ARN and does not re-encrypt all existing data. Record key references and preserve old keys throughout the lifecycle of ciphertexts and backups.

### 7.4. When an IAM key leaks

Containment may include:

- Deactivating the access key or revoking sessions depending on severity.
- Adding deny policies on affected resources/actions if needed.
- Rotating downstream credentials the principal could read.
- Reviewing CloudTrail, S3 data events if enabled, KMS events, IAM changes, and resource policies.
- Searching CI logs, artifacts, container images, Git history, and developer machines for the key.
- Checking for anomalous user/role/policy creation, access keys, bucket policies, or KMS grants.

Never assume CloudTrail logs all data events by default; verify actual logging configuration and visibility gaps.

## 8. Managing Azure Credentials and Key Vault

### 8.1. Microsoft Entra application credentials

For service principals/app registrations:

- Prefer managed identities for Azure workloads whenever possible.
- If using client secrets, create a new secret and update consumers before deleting the old secret unless compromised.
- Consider certificate credentials or federated identity credentials over client secrets.
- Restrict API permissions, app roles, tenants, and resources.
- Monitor sign-in logs/service principal sign-in logs.
- Delete old credentials after confirming consumers migrated.

Client secrets have expiration dates; configure alerts ahead of expiry. Never set excessively long lifetimes merely to reduce operational toil.

### 8.2. Managed identities

Managed identities eliminate client secrets in applications. The platform issues short-lived tokens to workloads. When revoking:

- Remove unneeded role assignments/RBAC or app roles.
- Disable/delete the identity when the workload is decommissioned.
- Revoke permissions at the appropriate resource scope.
- Check issued tokens/sessions and remaining validity per Entra/resource mechanics.
- Audit other workloads sharing the same identity.

Never share one managed identity broadly across unrelated services out of convenience. Separating identities shrinks the blast radius.

### 8.3. Azure Key Vault key and secret versions

Key Vault supports versioning for keys and secrets. Rotation requires coordinating consumers:

- Create a new version or configure a rotation policy.
- Consumers read the exact version or current version as designed.
- Verify key operations or secret retrieval succeed.
- Keep old versions while ciphertexts, certificates, or apps still depend on them.
- Revoke permissions of old principals when required.
- Enable soft-delete and purge protection per policy to prevent accidental deletion.

Key Vault key rotation does not automatically re-encrypt application-encrypted payloads. If a KEK protects DEKs, you can rewrap DEKs to the new version; if DEKs themselves must change, re-encrypt payloads.

### 8.4. Responding to exposed Azure credentials

- Revoke/delete the exposed client secret or certificate credential.
- Rotate to a new credential and update workloads.
- Disable the service principal or managed identity if compromise is severe and downtime is acceptable.
- Remove broad RBAC role assignments.
- Inspect Entra sign-in logs, audit logs, Key Vault diagnostic logs, and Azure Activity Log.
- Audit Key Vault accesses, secret versions, key operations, and resource modifications.
- If a Storage SAS leaks, determine the SAS type and signing key/policy; never assume every SAS revokes the same way.

## 9. Managing Google Cloud Credentials and Cloud KMS

### 9.1. Service account keys and Workload Identity

Prefer Workload Identity Federation or Workload Identity for workloads instead of long-lived service account JSON keys.

If a service account key must be used:

1. Create a new key per policy.
2. Update consumers/secret stores.
3. Verify workloads are using the new key.
4. Disable the old key.
5. Monitor errors and audits.
6. Delete the old key after verification.

Service account keys can be downloaded and copied; removing a file from a container does not revoke the issued key. You must disable/delete the key in IAM.

### 9.2. Disabling a service account vs. disabling a key

- Disabling a service account disrupts every workload using that identity.
- Disabling a specific key affects only that key credential.
- Removing an IAM binding alters principal permissions on resources.
- Token/session revocation has distinct semantics, and not all access tokens are invalidated instantaneously.

Scope the compromise before choosing an action. If a private JSON key leaked, disable that specific key promptly; if the entire service account identity is under attacker control, broader containment is needed.

### 9.3. Cloud KMS key versions

Google Cloud KMS symmetric keys consist of a `CryptoKey` and `CryptoKeyVersion` resources:

- Create a new version and update the primary version so new encryptions use the new version.
- Decrypting older ciphertexts still requires the older version to remain enabled.
- Disable an older version only after no data/backups depend on it or after rewrapping/re-encryption finishes.
- Destroying a version is irreversible once the destruction delay elapses.
- Rotation schedules create new versions; they do not automatically re-encrypt existing data.

Store the `CryptoKey` resource and version metadata according to your data format. Never delete an older version merely because the primary version changed.

### 9.4. Investigating compromise

Inspect Cloud Audit Logs, service account key creation, IAM policy changes, KMS encrypt/decrypt operations, service account impersonation, and workload identity federation. Review project/folder/organization scopes to identify inherited permissions an attacker could abuse.

## 10. Building Rotation-Aware Configuration in Spring Boot

### 10.1. Never place raw secrets in application.yml

Configuration should hold only references or secret names:

~~~yaml
app:
  integrations:
    payment:
      secret-reference: payment-provider/prod/webhook
      active-key-id: payment-2026-03
      previous-key-id: payment-2026-02
      previous-key-valid-until: 2026-12-01T00:00:00Z
~~~

These values are reference metadata. Never commit raw secrets, private keys, access tokens, or connection passwords into configuration files.

### 10.2. Separating secret retrieval from business logic

~~~java
import java.time.Instant;

public interface SecretVersionProvider {
    SecretValue get(String secretReference, String version);
}

public record SecretValue(
        String keyId,
        byte[] value,
        Instant createdAt,
        Instant expiresAt) {
}
~~~

Adapters can read from AWS Secrets Manager, Azure Key Vault, or Google Secret Manager. Business services depend on the interface rather than a specific cloud SDK.

In production:

- Defensively copy byte arrays.
- Never expose secrets via `toString`/logging.
- Govern cache TTLs and refresh behavior.
- Restrict which principals can read secrets.
- Configure timeouts, bounded retries, and appropriate circuit breakers.
- Never fall back to hardcoded secrets when the secret manager fails.
- If unable to authenticate safely, fail closed.

### 10.3. Verifying by key ID

When a sender supplies a key ID, the receiver selects only from currently permitted versions:

~~~java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.HashMap;
import java.util.Map;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class RotatingHmacVerifier {
    private final Map<String, byte[]> acceptedKeys;

    public RotatingHmacVerifier(Map<String, byte[]> acceptedKeys) {
        Map<String, byte[]> copy = new HashMap<>();
        acceptedKeys.forEach((id, key) -> copy.put(id, key.clone()));
        this.acceptedKeys = Map.copyOf(copy);
    }

    public boolean verify(
            String keyId,
            byte[] message,
            byte[] suppliedMac) throws GeneralSecurityException {

        if (keyId == null || message == null) {
            return false;
        }

        byte[] secret = acceptedKeys.get(keyId);
        if (secret == null || suppliedMac == null || suppliedMac.length != 32) {
            return false;
        }

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        byte[] expected = mac.doFinal(message);
        return MessageDigest.isEqual(expected, suppliedMac);
    }
}
~~~

This is an illustrative example. The map must be populated from time-valid permitted secret versions, excluding revoked keys. Never brute-try an unbounded list of secrets or accept arbitrary client-supplied key IDs without allowlist checks.

### 10.4. Refreshing secrets safely

Use scheduled refresh, Spring Cloud refresh mechanisms, or rolling deployments. Tailor the strategy to the credential type:

- Database passwords: update secrets and drain/recreate connection pools cleanly.
- OAuth client secrets: refresh token caches or client registrations, then verify new tokens.
- Webhook HMAC: receivers can accept two keys by key ID during overlap.
- TLS certificates: reload connectors/proxies and verify handshakes.
- KMS key references: update configuration after verifying decryption paths.

Do not refresh all secrets simultaneously if doing so creates a wide blast radius hard to roll back.

### 10.5. Do not retain credentials in heap longer than needed

Java cannot guarantee complete erasure of every internal byte array copy created by the JVM/crypto provider. Still, you can:

- Limit how long secrets live in memory.
- Never serialize secret objects.
- Restrict unapproved heap dumps/core dumps.
- Harden process access and debug endpoints.
- Never include secrets in exception messages.
- Use byte arrays with best-effort zeroization where feasible.
- Never cache credentials indefinitely.

## 11. Credential Exposure Response: Playbook

### 11.1. Pre-incident preparation

Prepare in advance:

- Credential inventory and owners/on-call contacts.
- Revocation procedures per provider and credential type.
- Controlled break-glass permissions.
- Audit logs and retention.
- Provider and security team contacts.
- Emergency rotation and rollback procedures.
- Downstream dependency lists.
- Backup/decryption test scenarios.
- Incident record and timeline templates.

Do not wait until a compromise occurs to figure out how to disable an access key or who owns a KMS key.

### 11.2. Detection and triage

Detection sources may include:

- Secret scanning flagging a key in Git.
- CI/CD logs or artifacts containing a secret.
- Provider alerts for anomalous access.
- Sign-in logs from unusual IPs/regions.
- Sudden API rate spikes.
- IAM roles/keys used outside normal schedules.
- Spikes in KMS decrypts or secret retrievals.
- Services failing because a credential expired or was revoked.

Triage must answer:

1. What credential type and which version/key ID?
2. Where was the secret exposed, since when, and who could access it?
3. Is the credential still active?
4. What scopes, resources, tenants, regions, and actions are granted?
5. Is there evidence of usage?
6. Could other secrets have been read from secret managers using this credential?
7. Was data read, exported, or altered?
8. Are there dependencies requiring coordination to avoid data loss or downtime?

When scope is uncertain, treat the credential as compromised until reliable evidence proves otherwise.

### 11.3. Containment

The goal is stopping attacker use of the credential and bounding the blast radius:

- Disable/revoke the exposed credential.
- Revoke associated refresh tokens/sessions or application grants.
- Add deny policies for the principal on resource policies if needed.
- Pause compromised workloads or endpoints.
- Rotate downstream credentials the attacker could have read.
- Block network paths or IPs when warranted.
- Revoke secret manager/KMS permissions for the compromised principal.
- Isolate containers/VMs/pods showing signs of takeover.
- Preserve evidence and logs needed for investigation.

**Do not immediately delete logs, container images, VMs, or Git history before capturing required evidence.** Containment prioritizes cutting off access; preserving evidence establishes scope and notification obligations.

### 11.4. Eradication

Once access is blocked:

- Remove secrets from code/configs/CI variables per procedure.
- Delete or replace artifacts/images containing credentials.
- Patch the leak source: debug logging, overly broad permissions, secret mounts, build output.
- Remove persistence mechanisms or attacker-created workloads/identities.
- Review IAM/RBAC/policies/grants and key access.
- Rotate credentials potentially exposed secondarily.
- Re-scan repositories, branches, tags, forks, packages, image registries, and build caches.

Removing a secret from Git history does not invalidate the old secret. Revoke first; rewriting history only reduces future exposure and cannot recall clones already downloaded.

### 11.5. Recovery

- Provision new credentials with least-privilege scope.
- Distribute via secret manager or workload identity.
- Deploy a canary, verify authentication and business flows.
- Gradually restore traffic.
- Confirm zero requests continue using the old credential.
- Restore KMS/key permissions under approved changes.
- Verify decrypt/restore of older data before disabling key versions.
- Monitor error rates, auth failures, audits, and anomalous usage.

### 11.6. Lessons learned

Post-incident:

- Document the timeline and root cause.
- Record affected credentials, resources, data, and principals.
- Assess whether customer/regulatory notifications are required under applicable obligations.
- Update inventories and rotation deadlines.
- Add secret scanning, least-privilege controls, alerts, and tests.
- Evaluate time to detect, contain, and recover.
- Never include raw secrets or sensitive data in incident reports.

## 12. Handling by Exposed Credential Type

| Exposed credential | Priority containment | Recovery and verification |
| --- | --- | --- |
| AWS IAM access key | Deactivate key; review CloudTrail and IAM changes | Create/prefer role-based identity, rotate downstream secrets |
| AWS STS session | Revoke/deny sessions per AWS mechanism; scope policies | Verify old sessions fail and updated workloads succeed |
| Azure client secret | Delete/revoke credential; check sign-in logs | Create new secret/certificate or migrate to managed identity |
| Azure managed identity | Remove role assignments/disable identity per blast radius | Provision new identity or narrow scope; inspect Activity/Sign-in logs |
| GCP service account key | Disable/delete the specific key | Migrate to Workload Identity; inspect Cloud Audit Logs |
| OAuth refresh token | Revoke token family/session | Issue new sessions; assess issued access tokens |
| JWT signing private key | Switch to a new key pair; assess signed tokens | Publish new JWKS; handle older tokens/denylist per threat model |
| Webhook HMAC secret | Move sender/receiver to new secret; reject old key if compromised | Verify signatures, key IDs, and event inbox |
| TLS private key | Replace key pair/certificate and revoke old cert | Update trust/handshakes; check clients still using old cert |
| KMS KEK | Assess data dependencies; disable only when emergency containment requires it | Rotate/rewrap DEKs; verify backups and decryption capability |
| DEK | Treat associated payloads as potentially exposed; mint new DEK and re-encrypt | Verify new ciphertexts; handle copies/backups per policy |
| Signed URL/SAS | Revoke grant/key/policy/resource by type | Inspect access logs; remember downloaded files cannot be pulled back from recipients |

## 13. KMS Compromise and Data Recoverability

### 13.1. KEK exposure is not the same as DEK exposure

If a KMS KEK is abused via decrypt permissions, an attacker can unwrap many DEKs. If raw KEK material is compromised, the scope can be even wider. If only a single DEK leaks, impact may stay bounded to an object/tenant depending on DEK granularity.

Determine:

- Which KMS operations occurred.
- Which principals invoked `Encrypt`/`Decrypt`/`GenerateDataKey`/`Wrap`/`Unwrap`.
- Whether encryption context/AAD was enforced properly.
- Which DEKs/objects depend on the key.
- Whether ciphertexts and wrapped DEKs were exfiltrated.

### 13.2. Rewrapping and re-encrypting

- **Rewrap DEKs:** unwrap the DEK with the old KEK and re-wrap with the new KEK. Payload ciphertext stays unchanged.
- **Re-encrypt payloads:** decrypt with the old DEK and encrypt again with a new DEK. Requires processing payloads and metadata.
- **Rotate KMS key material:** updates key material version per provider capabilities; does not necessarily change the key resource or re-encrypt old data.

If the KEK only needs changing per rotation policy, rewrapping may suffice. If a DEK leaked or algorithms/nonces were misused, rewrapping is not enough; you must re-encrypt payloads with a new DEK.

### 13.3. Disabling/destroying keys can cause data loss

Before disabling/destroying a key:

- Inventory objects, databases, backups, snapshots, replicas, and archives.
- Verify which key versions are required for decryption.
- Run a recovery test from backups.
- Check cross-region/cross-account dependencies.
- Identify retention/legal holds.
- Obtain approvals and file change records.
- Confirm keys/permissions can be restored if disabling.

Never destroy a KMS key merely because the primary version changed or live apps moved to a new key. Older backups may still need old keys for years.

### 13.4. When must downtime be accepted?

If a KEK suffers severe compromise, leaving decrypt enabled keeps the attack path open. Temporarily disabling the key and accepting service read downtime may be necessary. Coordinate the decision across security, service owners, data owners, and the incident commander based on blast radius and recovery readiness.

## 14. Testing Rotation, Revocation, and Incident Response

### 14.1. Rotation tests

- New credentials are generated and read from the secret manager.
- Canaries succeed with the new credential.
- Newly autoscaled instances do not revert to the old credential.
- Connection pools refresh/reconnect.
- Current/previous key overlap lasts the intended duration.
- Old credentials are revoked after cutover.
- Requests using old credentials are rejected post-revocation.
- Rollback is tested in a test environment when the old credential was not compromised.

### 14.2. Revocation tests

- Revoked API keys can no longer call APIs.
- Revoked OAuth refresh tokens cannot mint new access tokens.
- Old JWT keys no longer sign new tokens; verifiers handle old tokens per policy.
- Deactivated IAM access keys fail all new requests.
- Deleted/disabled Azure client secrets stop working.
- Disabled GCP service account keys fail.
- Old webhook secrets are rejected after overlap ends.
- Disabled KMS key versions fail decryption as expected and trigger alerts.

### 14.3. Recovery tests

- Restore exact secret versions from the secret manager.
- Restore certificate chains and private keys per approved procedure.
- Decrypt older envelopes with older key versions.
- Restore backups into an isolated environment.
- Rewrap DEKs and verify payload ciphertext does not change.
- Re-encrypt payloads and compare plaintext checksums.
- Verify outbox/inbox and event replays after service restarts.

### 14.4. Incident simulation

Simulate a credential appearing in CI logs:

1. Create a dedicated, narrowly scoped test key.
2. Record the simulated exposure location.
3. Execute deactivation/revocation per runbook.
4. Verify requests with the old key fail.
5. Provision a new credential and deploy a canary.
6. Search every place the secret was copied.
7. Verify audit evidence and timelines.
8. Measure time to contain and recover.

Never use production secrets in drills. Never paste real credentials into tickets or chat as examples.

### 14.5. Metrics and alerts

Monitor:

- Credentials nearing expiration.
- Time since last rotation.
- Old credentials still receiving requests post-cutover.
- Anomalous secret retrievals.
- Sudden spikes in failed authentications.
- Out-of-schedule IAM/RBAC changes.
- Unusual KMS decrypt/unwrap activity.
- Newly created service account keys/client secrets.
- Refresh token reuse or JWT validation failures.
- Failed or stuck pending rotation automations.

Alerts should specify an owner, severity, runbook, and escalation path. Never put raw secrets or tokens inside alert payloads.

## 15. Comprehensive Hands-On Exercise

`document-service` runs on Kubernetes and uses AWS S3/KMS, Azure Key Vault for an integration, and Google Cloud KMS in an analytics environment. A webhook HMAC secret and an OAuth client secret appear in CI logs.

**Tasks:**

1. Build an inventory of the service's credentials, keys, certificates, and principals.
2. Determine the permissions, consumers, and blast radius of both exposed secrets.
3. Deactivate/revoke the exposed credentials and verify new requests fail.
4. Inspect logs/audits for anomalous activity prior to revocation.
5. Create a new webhook secret and support a time-bounded overlap.
6. Rotate the OAuth client secret and evaluate already-issued access tokens.
7. Migrate workloads to managed identities/roles/workload identities where feasible.
8. Rotate the KEK in a test environment, rewrap DEKs, and verify backup decryption.
9. Check which objects/archives still depend on older KMS key versions.
10. Write an incident timeline, containment record, recovery evidence, and post-incident actions.
11. Set up alerts for credential expiration and stale key usage.
12. Run a non-production simulation.

**Self-assessment questions:**

- How does rotation differ from revocation?
- Why does deleting a secret from Git not invalidate the credential?
- Why is an overlap window helpful for rotation yet dangerous when a secret is compromised?
- Do access tokens issued before rotating an OAuth client secret expire immediately?
- How long must old JWT signing public keys be retained during rotation?
- Why are IAM roles/managed identities safer than static access keys?
- Does AWS KMS automatic rotation re-encrypt old objects automatically?
- Does creating a new Azure Key Vault key version automatically re-key existing ciphertexts?
- Does switching a GCP Cloud KMS primary version let you immediately disable the old version?
- Why can disabling a KMS key break backup readability?
- When a service account key leaks, is deleting the JSON file enough?
- When must downtime be accepted for containment?
- Why must incident response preserve evidence before deleting artifacts?

**Guided answers:** rotation transitions versions while revocation blocks credentials; Git history/clones keep exposed secrets so you must revoke first; overlap eases rollouts yet widens the window an old compromised key stays valid; older access tokens usually survive until `exp` or explicit revocation; verifiers need old public keys until older tokens expire or are invalidated; workload identities eliminate static secrets; KMS rotation does not automatically re-encrypt; new Key Vault/GCP versions do not migrate existing ciphertexts; disabling keys blocks decryption; deleting local files does not revoke cloud keys; downtime may be needed if attackers still hold access; evidence establishes blast radius and notification duties.

## 16. Official References

- [AWS IAM – Rotate access keys](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_access-keys-update.html): creating new keys, updating apps, deactivating, and deleting old keys.
- [AWS IAM – Revoke active IAM role sessions](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_revoke-sessions.html): limitations and revoking issued sessions.
- [AWS Secrets Manager – Rotation](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotating-secrets.html): version stages and rotation workflows.
- [AWS KMS – Rotate KMS keys](https://docs.aws.amazon.com/kms/latest/developerguide/rotate-keys.html): automatic/manual rotation and decrypting older ciphertexts.
- [Microsoft Entra – Add and manage application credentials](https://learn.microsoft.com/en-us/entra/identity-platform/how-to-add-credentials): client secrets, certificate credentials, and credential lifecycles.
- [Azure Key Vault – Configure key rotation](https://learn.microsoft.com/en-us/azure/key-vault/keys/how-to-configure-key-rotation): rotation policies and key versions.
- [Azure Key Vault – Soft-delete and purge protection](https://learn.microsoft.com/en-us/azure/key-vault/general/soft-delete-overview): protecting keys/secrets from accidental deletion or premature purging.
- [Google Cloud IAM – Service account key rotation](https://cloud.google.com/iam/docs/key-rotation): creating, updating consumers, disabling, and deleting keys.
- [Google Cloud IAM – Best practices for managing service account keys](https://cloud.google.com/iam/docs/best-practices-for-managing-service-account-keys): minimizing long-lived keys and replacing with workload identity.
- [Google Cloud KMS – Rotate a key](https://cloud.google.com/kms/docs/rotating-keys): primary `CryptoKeyVersion` and rotation workflow.
- [OAuth 2.0 Token Revocation – RFC 7009](https://www.rfc-editor.org/rfc/rfc7009): token revocation endpoint and semantics.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): inventory, lifecycle, rotation, access, and incident handling.
- [OWASP Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html): key lifecycle, backups, rotation, compromise, and destruction.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): protecting audit evidence and keeping credentials out of logs.

**Remember:** rotation replaces credentials on schedule; revocation shuts down untrusted credentials; incident response limits damage and verifies recovery. For cloud-integrated Spring Boot apps, prioritize workload identities, maintain inventories and audits, rotate secrets with safe overlap windows, revoke immediately on compromise, and disable/destroy encryption keys only after verifying all data and backups no longer depend on them.
