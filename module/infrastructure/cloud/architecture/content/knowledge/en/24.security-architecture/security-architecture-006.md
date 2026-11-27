# Managing Secrets, Certificates, Encryption Keys, and Rotation

Cloud applications need many sensitive values to connect to systems and protect data: database passwords, API tokens, private keys, TLS certificates, encryption keys, and workload credentials. If these values are stored in source code, images, configuration files, or logs, a single repository leak or overly broad permission can open paths into multiple systems. Even when secrets are stored securely, credentials without expiration, owners, or revocation procedures still create long-term risk.

**Secrets management**, **certificate management**, and **key management** are three related capabilities with distinct purposes. Secrets authenticate identities or grant access; certificates prove identity and help establish trusted channels; encryption keys protect data confidentiality or integrity. Rotation replaces old assets with new versions in a controlled way while keeping systems running and ensuring previously encrypted data remains readable.

This lesson belongs to the **Security Architecture** chapter of the **Cloud Architecture** track. The track teaches how to design cloud applications from business requirements through networking, compute, data, and deployment models, balancing reliability, security, scalability, cost, and operations. The content focuses on minimizing access privileges, managing credential lifecycles, protecting keys, and designing verifiable rotation.

After this lesson, you can:

- Distinguish secrets, credentials, certificates, public/private keys, and encryption keys.
- Design centralized secret stores, workload identities, and least-privilege access policies.
- Use KMS/HSM and envelope encryption appropriately.
- Manage TLS certificates, trust chains, expiration, renewal, and revocation.
- Design key hierarchies, key versions, rotation, and crypto-erasure.
- Rotate credentials without causing downtime or breaking connections.
- Detect leaks, revoke assets, investigate, and recover after compromise.
- Establish auditing, inventories, alerts, and SLOs for cryptographic assets.

## 1. Distinguishing Secrets, Certificates, and Encryption Keys

These assets can coexist within a single connection while solving different problems.

| Asset | Purpose | Examples | Risk if Exposed/Expired |
| --- | --- | --- | --- |
| Secret | Holds confidential values used to authenticate or gain access | DB password, API token, webhook signing secret | Others can impersonate or call APIs |
| Credential | Data/object representing access rights | Username/password, OAuth client credential | Privileges can be abused |
| Certificate | Binds an identity to a public key via a CA signature | TLS server certificate, client certificate | Loss of authentication or impersonation if private key leaks |
| Public key | Used to verify signatures or encrypt per algorithm | Public key inside a certificate | Typically non-secret, but source and fingerprint must be verified |
| Private key | Performs signing, decryption, or authentication per algorithm | TLS private key, signing key | Key exposure enables impersonation or decryption |
| Data encryption key (DEK) | Encrypts actual data | AES key for an object/database field | Corresponding data can be decrypted |
| Key encryption key (KEK) | Encrypts/wraps DEKs | KMS-managed key | Can unlock decryption of multiple DEKs |
| Root/CA key | Signs subordinate certificates or anchors a trust chain | Private key of an intermediate/root CA | Compromise can have system-wide impact |

A certificate is usually not secret; it contains a public key and identity metadata. The accompanying private key is the asset that must be protected. Encryption keys are also not like passwords: keys are consumed by cryptographic algorithms and require precise management of versions, usage, algorithms, lifecycles, and decrypt/unwrap permissions.

## 2. Threat Modeling and Asset Classification

Not every secret can be protected with the same level of control. Build an inventory and assess the impact if an asset is exposed, lost, modified, or becomes unavailable.

A minimal inventory should include:

- Asset ID and asset type.
- Accountable owner/team and consuming services.
- Purpose, environment, tenant, and resource scope.
- Secret reference or key ID; never include plaintext values in the inventory.
- Read, write, rotate, revoke, decrypt, and administer permissions.
- Creation date, current version, expiration date, and rotation schedule.
- Dependencies, active applications/clients, and rollback procedure.
- Data classification, impact level, and compliance requirements.
- Status: active, staged, deprecated, revoked, or destroyed.

For example, a production DB credential may be classified as critical because it grants write access to transactional data. A read-only metadata API token may carry lower impact, yet if shared across all tenants, its blast radius remains large.

### 2.1. Protection Tiers

| Tier | Examples | Typical Controls Required |
| --- | --- | --- |
| Critical | Root/CA private keys, payment signing keys, database admin credentials | Appropriate HSM or KMS, very narrow permissions, dual control, auditing, and emergency procedures |
| High | Production service credentials, DEKs/KEKs, TLS private keys | Secret manager/KMS, workload identity, rotation, and monitoring |
| Moderate | Scoped credentials for staging or read-only services | Central store, scoped access, expiration, and auditing |
| Public | Public certificates, public verification keys | Integrity/provenance, versioning, and proper distribution |

Classification must reflect exploitability and effective permission scope, not just asset names.

## 3. Centralized Secret Management

A secret manager/vault provides centralized storage, access control, versioning, auditing, and rotation integration. It reduces the need to embed secrets in repositories, images, or configuration files.

A secret management service typically supports:

- Encryption of secrets at rest and in transit.
- Access policies by workload identity, resource, environment, or tenant.
- Versioning and metadata.
- Audit logs for read/write/rotate/delete operations.
- Automatic rotation or rotation workflow integration.
- Secret injection or API retrieval.
- Expiration, revocation, and alerts.
- Replication/backup per service capabilities.

Centralization does not mean a single administrator or root credential can read every secret. Administrative privileges on the secret store should be separated by environment, tenant, business domain, and operation type.

### 3.1. Never Store Secrets in Source Code or Artifacts

Places that must not contain plaintext secrets:

- Git repositories, including private repositories.
- Docker images, VM images, or packages.
- Frontend bundles, mobile apps, or JavaScript sent to browsers.
- Terraform/CloudFormation plans/states without appropriate protection and lifecycle controls.
- CI/CD logs, build outputs, and crash dumps.
- Application logs, tracing attributes, or metric labels.
- Tickets, chats, wikis, or broadly shared operational docs.
- Test fixtures or database dumps used outside production.

Environment variables can serve as an injection mechanism in some runtimes, but do not make secrets inherently safe. They can leak via process inspection, crash dumps, debug endpoints, or logs if uncontrolled. Prefer identity-based retrieval or platform-native secret mounts/runtime integrations.

### 3.2. Secret References Instead of Values

Application configs should contain only references, such as a secret path/ARN/resource ID and version policy. At runtime when connecting, the application authenticates via workload identity and retrieves the secret within its authorized scope.

~~~yaml
database:
  host: db.internal.example
  credentialRef: secret://production/booking/database
  credentialVersionPolicy: current
tls:
  certificateRef: cert://production/booking-api
~~~

This is a conceptual example, not a standard provider URI. Secret managers and certificate managers have their own syntax. Never place plaintext passwords, tokens, or private keys directly into YAML.

## 4. Workload Identity and Least Privilege

An application should not share a broad static credential merely to retrieve other secrets. Authenticate workloads using platform-issued identities: IAM roles/service accounts, managed identities, SPIFFE/SPIRE identities, or equivalent mechanisms.

Conceptual flow:

~~~mermaid
sequenceDiagram
    participant W as Application workload
    participant I as Identity provider
    participant S as Secret manager
    participant D as Database

    W->>I: Request workload identity/token
    I-->>W: Short-lived identity token
    W->>S: Read authorized secret reference
    S-->>W: Secret value/version
    W->>D: Authenticate using scoped credential
~~~

Workload identity eliminates long-lived bootstrap passwords in configurations. However, trust policies must verify the specific service, namespace, environment, audience, and subject. Never grant read access to all secrets simply because a workload belongs to a cloud account/project.

### 4.1. Separating Permissions by Operation

Permissions to read secrets, create new versions, rotate, revoke, and delete are distinct rights.

- Runtime workloads usually only need read access to specific secrets.
- Rotation workers need permission to create new versions and update credentials at the target system.
- Operators may need to view metadata without reading plaintext values.
- Security administrators manage policies and audits, without necessarily using business credentials.
- Destroying keys or deleting versions requires special approvals/workflows.

### 4.2. Tenant-Aware Secret Access

In multi-tenant SaaS, secret references and policies must be tenant-bound. A runtime processing tenant A must not read tenant B's ERP credentials even if both tenants share a worker pool.

If a secret path includes a tenant ID, that only aids routing; the backend must still verify identity and policy. Never trust a client-supplied tenant ID to authorize secret access.

## 5. Secret Rotation and Credential Lifecycles

Rotation replaces an active credential with a new one while updating both the issuing system and consumers. The goal is to limit how long an exposed credential can be exploited and reduce the risk of long-lived secrets.

The lifecycle typically includes:

1. **Provision:** create the credential in the owning system.
2. **Store:** save the new version in the secret manager.
3. **Distribute:** authorize workloads to fetch the new version.
4. **Switch:** applications begin using the new credential.
5. **Verify:** confirm connections and business operations succeed.
6. **Revoke old:** revoke the old credential once consumers have switched.
7. **Audit/cleanup:** record version, timestamp, owner, and outcome.

Do not update the secret store and immediately revoke the old credential while applications still hold open connection pools or older workers. A bounded, monitored overlap window is required.

### 5.1. Two-Phase Rotation for Overlapping Credentials

~~~mermaid
flowchart TD
    A["Create credential B"] --> B["Store version B"]
    B --> C["Allow A and B temporarily"]
    C --> D["Refresh application clients"]
    D --> E{"All clients verified on B?"}
    E -- "No" --> F["Investigate / retry / rollback window"]
    F --> D
    E -- "Yes" --> G["Revoke credential A"]
    G --> H["Close overlap and audit"]
~~~

Not every system allows two concurrent credentials. For a single database password, two database users or a staged credential mechanism may be needed to avoid downtime. Design rotation around the target system's capabilities.

### 5.2. Rotation Cadence and Event-Driven Rotation

No single rotation cadence fits every secret. Policies should weigh:

- Impact if the credential is exposed.
- Whether the credential already has an expiration.
- Provider support for automated rotation.
- Number of consumers and update lead time.
- Ability to revoke immediately.
- Compliance and organizational policies.
- Cost and outage risk from rotating too frequently.

Beyond scheduled cadences, rotate immediately upon suspected compromise, staff/vendor permission changes, scope expansion, or accidental commits/logging of credentials.

## 6. Dynamic Secrets and Short-Lived Credentials

Dynamic secrets are generated on demand, carry a TTL, and automatically expire or are revoked when the lease ends. Examples include a secret manager issuing temporary database users for a service or short-lived cloud access tokens.

Benefits:

- Shrinks the window in which a credential can be exploited.
- Eliminates long-lived secrets in configurations.
- Each workload/lease can be audited individually.
- Reduces the need for large-scale static rotation.

Trade-offs:

- Runtimes must handle expiration, renewal, and revocation.
- Target databases/systems must support dynamic credential creation.
- If the secret manager becomes unavailable, issuing new credentials may fail.
- Connection pools must refresh before credentials expire.
- High volumes of temporary users/roles can strain database limits.

### 6.1. TTL Must Exceed Request Needs While Remaining Risk-Bounded

A TTL that is too short increases requests to the secret manager and causes failures when dependencies slow down. A TTL that is too long erodes the benefit of ephemeral credentials. Provide a renewal window, jitter, safe caching, and defined behavior when renewal fails.

Never log a short-lived token just because it is about to expire; while valid, the token remains exploitable.

## 7. Managing TLS Certificates

TLS certificates prove server/client identity and bind a public key to an identity via a CA signature. Systems commonly use server certificates so clients can verify endpoints; mTLS requires both sides to verify each other's certificates.

Components:

- **Subject/SAN:** DNS names or identities the certificate represents.
- **Public key:** the public key embedded in the certificate.
- **Private key:** the corresponding secret key used in the TLS handshake per algorithm.
- **Issuer/CA:** the organization or authority that signed the certificate.
- **Validity period:** the time range during which the certificate is valid.
- **Certificate chain:** chain of certificates from leaf to intermediate/root trust anchor.
- **Key usage/EKU:** constraints on permitted cryptographic uses.
- **Revocation mechanism:** revocation status via CRL/OCSP or corresponding policies.

### 7.1. Certificate Lifecycle

A typical lifecycle:

1. Generate the private key in a suitably protected environment.
2. Create a CSR with accurate SANs and key usages.
3. Submit the CSR to a trusted CA.
4. Receive the certificate and chain.
5. Validate names, chain, expiration, usages, and key pair match.
6. Deploy the certificate/key to endpoints.
7. Verify TLS handshakes from representative clients.
8. Monitor expiration and renew ahead of deadlines.
9. Revoke if the private key is compromised or the certificate is no longer trusted.
10. Delete/disable the private key per retention and forensic policies.

Do not reuse the same private key across all services or all tenants unnecessarily. Key reuse expands the blast radius when one endpoint is compromised.

### 7.2. SAN and Hostname Validation

Certificates must include the exact DNS names/IPs clients connect to in the Subject Alternative Name (SAN) extension. A certificate signed by a trusted CA without a matching hostname must still be rejected by clients. Never disable hostname verification to "fix" certificate mismatch errors in production.

### 7.3. Chains and Trust Stores

A leaf certificate may be valid while clients distrust the intermediate/root CA or the server fails to send the full chain. Verify trust stores across all clients/runtimes, especially when switching CAs, rotating intermediates, or upgrading base OS images.

## 8. Zero-Downtime Certificate Renewal and Rotation

An expired certificate prevents clients from connecting even when the application and network are completely healthy. Configure alerts by remaining days, automate renewal, and deploy sequentially.

An overlapping rollout process:

- Issue the new certificate and corresponding private key.
- Verify SANs, chain, key usages, and key pair match.
- Install the new certificate on a subset of instances/cells.
- Perform TLS handshakes from real clients.
- Expand deployment by cohort.
- Ensure load balancers/proxies and backends all hold compatible certificates.
- Maintain a rollback path for a controlled window.
- Revoke old certificates/keys if needed and audit completion.

When clients pin certificates or public keys, rotation must also update pinsets using an overlap strategy. Never simply swap a server certificate and assume all clients will accept it.

### 8.1. Expiry Monitoring

Monitor at minimum:

- Certificate expiration date and days-to-expiry.
- SAN/hostname mismatches.
- Issuer/chain/trust status.
- Renewal job successes/failures.
- TLS handshake failure rates.
- Active certificate version per endpoint/region/cell.
- Client pinning compatibility if applicable.

Alerting only with 1 day left can be too late if renewal pipelines require approvals or deployment windows. Set thresholds based on recovery lead time and release schedules.

## 9. mTLS and Service-to-Service Identity

In microservices or zero-trust environments, mTLS can authenticate both clients and servers. Each workload holds a distinct identity certificate, and policies govern which services may call which services.

mTLS does not replace business authorization. Certificates prove workload identity, while policies still determine allowed actions and resources. An authenticated service may still be forbidden from reading tenant data or calling administrative operations.

Manage:

- CA trust hierarchies and issuance policies.
- Workload identity/SAN mappings.
- Certificate TTLs and automatic renewal.
- Rotation without causing simultaneous trust mismatches.
- Revocation and key compromise response.
- Sidecar/service mesh control-plane availability.
- Auditing of identities and policy decisions.

## 10. Encryption Keys and KMS

A Key Management Service (KMS) provides lifecycle and policy controls for cryptographic keys: creation, storage, usage, rotation, disabling, and auditing. Some workloads require a Hardware Security Module (HSM) to protect key material within compliant hardware or perform sensitive operations inside a controlled boundary.

A KMS/HSM does not decide which data needs encryption, who may decrypt, or how to recover if a key is disabled. Application and data architectures must still define scope, key policies, and recovery.

### 10.1. Key Concepts

- **Symmetric key:** the same key encrypts and decrypts; performance suits many data workloads.
- **Asymmetric key pair:** public/private keys used for signing/verification or encryption/decryption per algorithm.
- **DEK:** key encrypting payloads/data.
- **KEK/wrapping key:** key used to wrap DEKs.
- **Root/master key:** top-level key protecting other keys or anchoring a hierarchy by design.
- **Signing key:** key signing artifacts, tokens, messages, or certificates.

Never use a single key for all purposes. Key separation and algorithm/key-usage constraints reduce cross-purpose risk.

### 10.2. Envelope Encryption

Instead of calling KMS for every byte of data, applications can use envelope encryption:

1. KMS creates or protects the KEK.
2. The application obtains a DEK or asks KMS to generate a data key.
3. The DEK encrypts the payload using an appropriate algorithm.
4. The DEK is wrapped with the KEK.
5. Store ciphertext, wrapped DEK, key ID, and encryption metadata.
6. To decrypt, authorize KMS to unwrap the DEK, then decrypt the payload.

~~~mermaid
flowchart TB
    KMS["KMS / KEK"] -->|Wrap DEK| W["Wrapped DEK"]
    DATA["Plaintext data"] --> ENC["Authenticated encryption"]
    DEK["Data encryption key"] --> ENC
    ENC --> CT["Ciphertext"]
    W --> STORE[("Ciphertext + wrapped DEK + key metadata")]
    CT --> STORE
    STORE --> DEC["Decrypt with unwrapped DEK"]
    KMS -->|Unwrap DEK| DEC
    DEC --> OUT["Plaintext"]
~~~

Envelope encryption reduces KEK calls on large datasets and supports key hierarchies. Record algorithm, nonce/IV, authentication tag, key version, and associated data in a well-defined format. Never invent cryptographic primitives.

### 10.3. Authenticated Encryption

When encrypting application data, prefer authenticated encryption modes supported by trusted libraries/standards, such as AES-GCM or ChaCha20-Poly1305 where appropriate for the environment. Nonces must strictly obey uniqueness rules per key/mode. If nonce reuse occurs in certain modes, confidentiality and integrity can break catastrophically.

Never hand-stitch encryption and MAC in ad-hoc code or use ECB for application data.

## 11. Key Policies and Separation of Duties

KMS policies should separate duties:

- Who can create keys?
- Who can use keys to encrypt?
- Who can decrypt/unwrap?
- Who can rotate?
- Who can disable/revoke?
- Who can modify policies/grants?
- Who can schedule destruction?
- Who can restore or create replica keys in another region?

Application runtimes typically need permission to use specific keys, not administer keys. Operators may need metadata visibility without decrypting data payloads. Disable/destroy operations should require approvals and guardrails.

Root/CA keys or keys protecting critical data may require HSMs, multi-party control, or dual authorization per organizational policy.

## 12. Key Rotation: Changing Keys While Keeping Old Data Readable

Key rotation has at least two meanings:

1. Creating a new key version for encrypting new data.
2. Re-encrypting old data with a new DEK/key or rewrapping existing DEKs with a new KEK.

These are distinct operations. In envelope encryption, rotating a KEK may only require unwrapping DEKs and rewrapping them under the new KEK without decrypting entire payloads. Rotating a DEK usually requires decrypting and re-encrypting payloads.

### 12.1. KEK and DEK Rotation

| Operation | Ciphertext Data | Wrapped DEK | Cost |
| --- | --- | --- | --- |
| Switch key version for new encryptions only | Old ciphertext unchanged | New metadata for new DEKs | Lower |
| Rewrap DEK | Ciphertext unchanged if format supports it | Rewrapped with new KEK | Usually lower than full re-encryption |
| Rotate DEK / re-encrypt | Produces new ciphertext | New DEK and new wrapped DEK | Higher; requires reading/writing data |
| Disable/destroy old KEK too early | Old data may become unreadable | Old DEKs cannot be unwrapped | Risk of permanent decryption loss |

Note: if cryptographic erasure is required, remove access to key material through a controlled procedure. Never destroy a key merely because a new key version was created; verify no active data or backups still require the old key.

### 12.2. Versioned Key Metadata

Encrypted records should store the key ID/version or wrapped DEK metadata needed for decryption. Do not rely solely on an alias pointing to "current key" without persisting historical version references. Aliases can change, while old ciphertexts must retain enough metadata to decrypt throughout the retention lifecycle.

## 13. Rotation Plans by Asset Type

| Asset | Common Rotation Method | What to Verify |
| --- | --- | --- |
| Database password | Create new user/credential, update pools, verify, revoke old | Old connections, in-flight transactions, permission parity |
| API token | Create second overlapping token, deploy clients, revoke old token | Whether provider supports overlap and token quotas |
| OAuth client secret | Add new secret, update client, observe token issuance, retire old | Cached configs and token lifetimes |
| TLS certificate | Issue new cert/key, deploy by cohort, verify handshakes, revoke if needed | SAN, chain, pinning, load balancers, and client trust |
| mTLS workload cert | Issue new identity cert, update trust overlap, refresh workloads | CA rotation, sidecars/caches, and expiration |
| KMS KEK | Create new version/key, switch encryptions or rewrap DEKs | Backups, old ciphertexts, cross-region key access |
| DEK | Re-encrypt data or version per object/record | Throughput, integrity, rollback, and metadata |
| Signing key | Publish new public key, sign with new private key, verify overlap, retire old | JWT/token lifetimes, client trust, and signature key IDs |

Rotations without overlap require a specific protocol to avoid downtime. For instance, a database supporting only one password per user may need a second user account so connections can migrate before changing or removing the first.

## 14. Implementing Zero-Downtime Rotation

A general workflow can include:

1. **Inventory:** locate all consumers, caches, connection pools, regions, and jobs using the old version.
2. **Prepare:** create the new version, check policies/permissions, and confirm the target accepts it.
3. **Overlap:** allow old and new versions to coexist briefly if supported by the target.
4. **Rollout:** update workloads via canary/cohorts; refresh secret/certificate/key references.
5. **Observe:** monitor auth failures, handshakes, error rates, connections, and decryption successes.
6. **Commit:** confirm every consumer is using the new version.
7. **Revoke:** invalidate the old version at the source of authority.
8. **Verify revocation:** test that the old credential is rejected and no consumers still use it.
9. **Close:** update inventory, audits, and rotation timestamps.

### 14.1. Preventing Caches from Holding Stale Secrets

Applications may cache secrets or hold connection pools open longer than a secret's TTL. Implement pre-expiry refresh, version-event invalidation, or controlled restarts/draining. Avoid refreshing all instances simultaneously if the secret manager has tight rate limits; use jitter and staged rollouts.

### 14.2. Rollback During the Overlap Window

If a new credential fails, you can temporarily fall back to the old credential provided it has not been revoked and shows no signs of compromise. If rotation was triggered by secret exposure, never roll back to the exposed credential; fix forward with a fresh asset and constrain traffic.

## 15. CA Certificate Rotation and Trust Transitions

Rotating leaf certificates is usually simpler than rotating CAs. When a CA or intermediate changes, clients may need to trust both old and new chains during a transition period.

A trust transition procedure:

1. Publish or deploy the new trust anchor/intermediate to clients.
2. Verify clients trust both required chains.
3. Switch server/client certificates to the new chain by cohort.
4. Monitor handshakes and certificate validation.
5. Confirm no endpoints still serve the old chain.
6. Remove the old trust anchor on schedule.
7. Revoke old certificates if compromised.

Removing the old CA before all endpoints/clients finish migrating causes widespread connection failures. Leaving a compromised trust anchor active too long lets attackers continue minting trusted certificates. Overlap windows must have hard deadlines and monitoring.

## 16. Compromise Response: Suspected Secret or Key Exposure

When credential/key exposure is suspected, prioritize halting further access and preserving evidence.

Conceptual workflow:

1. Identify the asset, permission scope, and suspected exposure window.
2. Identify workloads, tenants, repos, logs, endpoints, and data that could have been accessed.
3. Disable/revoke or replace according to severity.
4. Fence active sessions/tokens/connections where supported.
5. Issue new credentials/keys and roll out via emergency procedures.
6. Rotate downstream secrets that could have been read using the exposed credential.
7. Inspect audit logs, API calls, database access, and accessed/modified data.
8. Search for secret traces in Git history, artifacts, logs, and backups; remediate per retention/security policies.
9. Rotate dependent credentials and keys if chained compromise is possible.
10. Verify old credentials no longer work, update the incident record, and strengthen controls.

Simply deleting a secret from the latest commit is not enough; values committed to Git history or stored in artifacts remain accessible. Once a secret appears publicly, treat it as compromised until proven otherwise; rotate/revoke first, then clean history per policy.

### 16.1. Private Key Compromise

When a TLS/signing private key is exposed, determine which certificates/tokens were issued or signed during that window. Certificate revocation may require CRL/OCSP or trust policy updates; rotating a key while clients still trust the old CA/chain does not automatically revoke exposed certificates.

For signing keys, manage key IDs, verify key rotation, and check lifetimes of issued tokens. Revoking tokens/sessions or shortening trust windows may be necessary depending on token type.

## 17. Crypto-Erasure and Key Destruction

Crypto-erasure destroys key material so ciphertexts can no longer be decrypted with that key, when technical and policy conditions allow. It can assist data deletion, but requires extreme care.

Before destroying a key, verify:

- Does the key protect any other data?
- Do any replicas, backups, or archives still need the key?
- Are there legal holds or retention requirements?
- Does any key escrow or recovery material still exist?
- Is the operation irreversible?
- Who approves and who executes?
- Which key ID, timestamp, and scope does audit evidence record?

Disabling a key temporarily blocks usage while allowing recovery; scheduling destruction and actual destruction have distinct semantics. Never confuse the two states. Irreversible key destruction can cause permanent data loss.

## 18. Backups, Restores, and Key Accessibility

Encrypted backup data without its key or access to the corresponding KMS/HSM is not a recoverable backup. DR plans must protect both data and decryption capability simultaneously.

Verify:

- Are keys replicated to DR regions per policy?
- Do KMS policies allow recovery workloads to use the keys?
- Do identities, roles, and networks to KMS work during DR?
- Do old key versions stay enabled throughout required retention periods?
- Does backup metadata include key ID/version and algorithm?
- Can HSM quorum/backup key material be recovered per procedure?
- Have restore tests successfully decrypted real backup data?

If a key lives in another region/account, failing over compute without key access can prevent applications from reading databases or objects.

### 18.1. Recovery Keys and Break-Glass

Some critical keys require break-glass procedures separated from routine operations. These procedures should enforce dual control, time limits, auditing, notifications, and post-event reviews. Never store a copy of a master key in a wiki or shared drive "just in case KMS goes down."

## 19. Auditing, Monitoring, and Alerting

Secrets, certificates, and keys must be monitored like production resources.

| Metric/Signal | Meaning |
| --- | --- |
| Secret age / last rotation | How long a credential has existed |
| Expiry days | Days remaining for a certificate/credential |
| Rotation success/failure | Whether rotation workflows complete |
| Active version distribution | Which versions workloads are using |
| Secret read anomalies | Workloads reading secrets unusually |
| Access denied spikes | Policy, identity, or configuration issues |
| Certificate handshake failures | Chain, expiration, hostname, or key mismatches |
| KMS throttling/latency | Impact on encryption/decryption paths |
| Key disable/destroy events | Sensitive operations requiring audit |
| Decrypt failures | Incorrect metadata/key version or permissions |
| Orphaned assets | Secrets/keys/certificates with no owner/consumer |
| Revoked credential usage | Consumers still attempting to use old credentials |

Alerts must be classified by severity and linked to owners/runbooks. An upcoming certificate expiration does not carry the same urgency as mass decryption failures or secret reads from an unfamiliar workload.

Never put plaintext, private keys, tokens, or secret values into metric labels or logs. Audits record asset ID, principal, action, result, timestamp, and relevant context—never the secret itself.

## 20. Rotation Configuration and Policy as Code

Rotation policies should be versioned and tested like other code/configs. Conceptual policy example:

~~~yaml
assetPolicy:
  type: databaseCredential
  owner: booking-platform
  maxAgeDays: 60
  access:
    workloadIdentity: booking-api-prod
    secretRef: production/booking/database
    operations:
      - read
  rotation:
    mode: staged
    overlapHours: 4
    verifyConnectionBeforeRevoke: true
  alerts:
    beforeExpiryDays: [14, 7, 2]
~~~

This is an illustrative structure, not a standard schema. Actual policies must account for target capabilities, TTLs, secret manager behavior, workload restarts, and business requirements.

Policy-as-code can verify:

- Secrets are not shared in violation of policy.
- Certificates meet SAN and expiration standards.
- Keys use approved algorithms and key sizes.
- Runtime identities lack administrative permissions.
- Rotation policies specify owners and deadlines.
- Production secrets are not referenced from staging.
- Key destruction requires approval and retention validation.

## 21. Architecture Example: Booking API and Payment Connector

A SaaS platform includes a booking API, database, payment provider, and per-tenant ERP connectors.

### 21.1. Asset Design

- Booking API uses workload identity to obtain scoped database credentials.
- Database passwords rotate in two phases; connection pools refresh gradually.
- API server certificates are issued and auto-renewed by a certificate manager.
- Internal service communication uses mTLS with appropriately TTL-bound workload identity certificates.
- Payment connector secrets are isolated per tenant in the secret manager; runtimes read only the authenticated tenant's secret.
- Sensitive customer/payment data is encrypted with DEKs; DEKs are wrapped by a KEK in KMS.
- Key ID/version is stored alongside ciphertext metadata for historical decryption.
- KMS policies separate encrypt/decrypt usage from key administration.
- Rotation/revocation includes auditing, alerts, and runbooks.

~~~mermaid
flowchart TB
    APP["Booking API workload"] --> ID["Workload identity"]
    ID --> SM["Secret manager"]
    SM --> DBSEC["DB credential"]
    DBSEC --> DB[("Transactional database")]
    APP --> CERT["Certificate manager"]
    CERT --> TLS["TLS / mTLS identity"]
    APP --> KMS["KMS / HSM"]
    KMS --> KEK["KEK"]
    APP --> DEK["DEK for data"]
    DEK --> DATA["Encrypted data"]
    KEK --> WRAP["Wrapped DEK"]
    APP --> TRES["Tenant-scoped secret reference"]
    TRES --> SM
    SM --> PAY["Payment / ERP credentials"]
~~~

The diagram illustrates conceptual relationships; in practice, applications typically ask KMS to generate/wrap DEKs rather than reading plaintext KEKs directly. KMS/HSM should keep key material inside the service boundary.

### 21.2. Database Credential Rotation Scenario

1. Rotation worker authenticates with its dedicated workload identity.
2. Create database user B with equivalent permissions to user A and proper scope.
3. Store credential B as a new secret version.
4. Roll out Booking API by cohort, opening new connections with B.
5. Monitor connection successes, query errors, and transaction health.
6. Confirm no instances remain on user A.
7. Revoke user A and test authentication to verify rejection.
8. Update inventory/audit logs and retire the old version per retention policy.

If a DB only supports a single password per user, use credential transition features or a second account; changing a password directly while old connections live can trigger hard-to-control failures.

### 21.3. Certificate Renewal Scenario

1. Certificate manager renews the leaf certificate ahead of expiration.
2. Verify chain/SAN/key pair.
3. Deploy to a canary instance.
4. Run client handshakes and monitor errors.
5. Roll out to remaining instances/proxies.
6. Verify all endpoints serve the new certificate.
7. Revoke the old certificate if needed; update inventory.

## 22. Common Design Mistakes

| Mistake | Consequence | Prevention |
| --- | --- | --- |
| Hardcoding secrets in repos/images | Leaks via Git/artifacts | Secret manager and workload identity |
| Sharing one credential across services | Large blast radius, poor attribution | Separate identities/secrets per workload |
| Storing private keys beside certificates in shared buckets | Multiple parties can impersonate endpoints | KMS/HSM or tightly restricted secret store |
| Rotating store first and immediately revoking target | Existing connections/consumers break | Overlap window, staged rollout, and verification |
| Only creating a new key version | Old ciphertexts may still depend on old keys | Plan rewrap/re-encryption and retention |
| Destroying KEK while backups still need it | Data becomes unrecoverable | Dependency inventory and restore testing |
| Renewing certificates without testing chains | Client handshakes fail | Canary handshakes and trust-store validation |
| Disabling hostname verification | Opens door to MITM | Fix SAN/DNS/certificate chains properly |
| Long-lived config/feature caching of secrets | Old secrets remain active uncontrollably | TTLs, version refresh, and revocation |
| Logging tokens/keys | Creates extra secret copies | Redaction and secret scanning |
| Not tracking expirations | Expired certificates cause outages | Inventory and pre-expiry alerts |
| Reusing one key for encryption and signing | One compromise hits multiple functions | Key separation and usage policies |
| Granting runtime workloads KMS admin rights | Workloads can disable/destroy keys | Least privilege, separation of duties |
| Rotation without an owner | Overdue credentials or abandoned workflows | Owners, SLOs, and escalation |
| DR lacks KMS access | Restores have ciphertext but cannot decrypt | DR identity/key access testing |

## 23. Design and Implementation Process

1. **Inventory:** catalog secrets, certificates, private keys, DEKs/KEKs, and owners.
2. **Classify:** assess impact, permission scope, tenant/environment, and retention.
3. **Select management tooling:** secret manager, certificate manager, KMS/HSM by asset type.
4. **Design identity:** workload identity, audience, trust policies, and least privilege.
5. **Design storage/references:** avoid embedded plaintext, enforce versioning, and separate secrets from config.
6. **Define lifecycles:** expiration, rotation cadence, emergency revocation, destruction, and owners.
7. **Design rollouts:** overlap, staged refresh, connection draining, verification, and rollback windows.
8. **Protect data:** envelope encryption, metadata/versioning, and key separation.
9. **Design certificate trust:** CA chains, SANs, mTLS, renewal, and pinning transitions.
10. **Establish monitoring:** age, expiry, active versions, failed auth, KMS latency, and auditing.
11. **Prepare for incidents:** compromise workflows, dependent secret rotation, and forensic evidence.
12. **Test DR:** restore ciphertext, access keys, verify certificates, and use credentials in the recovery region.
13. **Periodic review:** orphaned secrets, stale versions, permission drift, and key lifecycles.

## 24. Well-Architected Evaluation

| Perspective | Design Questions |
| --- | --- |
| **Reliability** | Do rotations have overlap and rollback? Are secret manager/KMS HA? Are certificate expiries and key dependencies tracked? Have DR restores been decrypted? |
| **Security** | Are workload identity and least privilege enforced? Are private keys/secrets centralized? Are key usages separated? Are audits and revocations effective? |
| **Performance Efficiency** | Do secret retrieval/caching, KMS latency, and connection refreshes impact requests? Do rotations cause load spikes? |
| **Cost Optimization** | Are KMS/HSM calls, certificate issuances, secret versions, and storage controlled? Does protection match impact? |
| **Operational Excellence** | Does inventory have owners? Are rotation status, expiry, orphaned assets, and incident runbooks observable? |

### Acceptance Checklist

- [ ] Secrets/certificates/keys have an inventory, owner, purpose, environment, and classification.
- [ ] Plaintext never appears in source, images, frontends, logs, or tickets.
- [ ] Runtimes use workload identity with specific read permissions.
- [ ] Secret manager separates read, write, rotate, revoke, and administer permissions.
- [ ] Secrets and connector credentials are scoped per tenant/environment.
- [ ] Certificates have valid SANs, trust chains, key usages, and expiry monitoring.
- [ ] TLS hostname verification is enabled; mTLS identity maps to authorization.
- [ ] KMS/HSM policies separate encrypt/decrypt from key administration.
- [ ] DEK/KEK hierarchy and envelope metadata are explicitly versioned.
- [ ] Rotations use staged rollouts, overlap, verification, and old-version revocation.
- [ ] Caches/connection pools refresh ahead of expiration; renewal failures are handled.
- [ ] Compromise response revokes tokens/sessions and checks dependent secrets.
- [ ] Key disable/destroy requires approval, retention validation, and auditing.
- [ ] Backup/DR has KMS/key access and has successfully decrypted restored data.
- [ ] Alerts detect overdue credentials, stale versions, and anomalous access.
- [ ] Rotation/restore/incident runbooks have owners and have been rehearsed.

## 25. Applied Exercise

An equipment-rental SaaS platform serves 300 tenants. Each tenant can connect an ERP and a payment gateway. The Booking API uses static database credentials; the API gateway has a TLS certificate expiring in 20 days; contract profile data is encrypted with DEKs wrapped by a KEK in KMS. A connector secret is discovered inside the CI logs of a private repository.

Design the following:

1. Classify secrets, certificates, private keys, DEKs, and KEKs; assign asset owners.
2. Design workload identity so the Booking API reads only the right database secret and tenant-scoped connector secrets.
3. Define an incident response workflow for the secret leaked in CI logs covering revocation, rotation, auditing, and checking dependent credentials.
4. Plan DB credential rotation without disrupting connection pools.
5. Plan TLS certificate renewal and chain/SAN verification prior to rollout.
6. Explain how to rotate the KEK and decide whether to rewrap DEKs or re-encrypt data.
7. Identify which data/backups still depend on old keys and when destruction is permitted.
8. Design alerts for certificate expiry, secret age, rotation failures, and KMS access anomalies.
9. Test DR in another region to prove encrypted backups can be decrypted.
10. Specify which privileges require dual control/break-glass and separate auditing.

A strong solution revokes the exposed secret promptly, provisions fresh credentials rolled out by tenant/cohort; isolates connector secrets per tenant; renews certificates ahead of expiry with canary handshakes; uses envelope encryption with stored key version metadata; and retires the old KEK only after verifying required data and backups have been rewrapped/re-encrypted or passed retention.

**Core Takeaway:** secrets authenticate access, certificates establish identity trust, and encryption keys protect data or signatures. Safe management requires inventory, workload identity, least privilege, versioning, auditing, and revocation workflows. Rotation is only complete when consumers have switched over, old versions are verifiably disabled, and historical data remains recoverable per policy.
