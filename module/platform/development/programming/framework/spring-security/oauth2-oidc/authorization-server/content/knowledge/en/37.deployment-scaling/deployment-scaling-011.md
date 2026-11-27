# Backup, Disaster Recovery, and Signing Key Incident Response Plan

The Authorization Server is the trusted component in an OAuth 2.0 / OpenID Connect system. If the server goes down, clients may be unable to start login flows, exchange authorization codes, or refresh tokens. If the database is lost, the server may no longer know which authorizations, consents, and refresh tokens exist. If a signing key is lost or compromised, JWT issuance and verification can be disrupted or cease to be trustworthy.

For Spring Authorization Server, a recovery plan must simultaneously protect business data, signing keys, issuer configuration, client secrets, and the infrastructure needed to serve endpoints. A standalone database backup is not enough to restore a safely operating Authorization Server.

## 1. Defining recovery objectives and incident scope

Before selecting backup technologies, the operations team must agree on two metrics:

- **RPO (Recovery Point Objective)**: the maximum amount of data loss tolerable, measured in time. An RPO of 5 minutes means that after an incident, restored data may miss at most roughly the last 5 minutes of transactions.
- **RTO (Recovery Time Objective)**: the maximum time allowed to bring the service back to an operational state meeting requirements. An RTO of 30 minutes means the goal is restoring service within 30 minutes of confirming the incident.

RPO and RTO must be defined according to the impact of each data type. An Authorization Server might tolerate having to ask users for consent again in some scenarios, but it cannot arbitrarily resurrect revoked refresh tokens. Likewise, signing keys can be stored in an HSM or KMS with its own redundancy, while the database is recovered from backups and transaction logs.

Classify scenarios before writing runbooks:

| Scenario | Primary impact | Response goal |
|---|---|---|
| Single instance or node fails | Reduced serving capacity | Shift traffic to healthy nodes |
| Loss of a deployment region | Service unavailable in that region | Fail over to DR region |
| Database corruption or data loss | Loss of authorizations, consents, clients, or token state | Restore consistent data |
| Loss of access to signing keys | Unable to sign new tokens | Restore key access or activate backup key |
| Signing key compromised | Tokens may be forged | Isolate key, rotate keys, and handle affected tokens |
| Configuration or TLS certificate error | Endpoints or trust chains fail | Restore valid configuration and certificates |

High availability (HA) and disaster recovery (DR) solve two different problems. HA reduces disruption from single-instance or single-component failures; DR recovers from major incidents losing an entire region, data, or cryptographic assets. A multi-replica cluster sharing one database can still suffer a total outage if the database or KMS in that region goes down.

## 2. Inventorying assets that must be backed up

Catalog assets, owners, storage locations, sensitivity levels, backup frequencies, and recovery methods. For Spring Authorization Server, consider at minimum:

| Asset | Contents to protect | Consequence if missing |
|---|---|---|
| Registered clients | Client ID, redirect URIs, grant types, authentication methods, scopes, token settings | Clients cannot authenticate or request proper permissions |
| Authorization records | Authorization codes, access tokens, refresh tokens, token status, and related metadata | Refresh, revocation, introspection, or authorization audit trails are broken |
| Consent records | Principal, client, and approved authorities | Users may have to re-consent or approval state becomes inaccurate |
| Signing keys | Private keys or key usage rights in KMS/HSM; key IDs, algorithms, and lifecycle state | Cannot sign JWTs or risk losing verification of older tokens |
| Issuer configuration | Issuer URI, endpoints, algorithms, TTLs, token policies | OIDC/OAuth2 metadata becomes inconsistent with issued tokens |
| Application secrets | Secrets for DB, KMS/HSM, encryption, queues, and auxiliary services | Service cannot connect to dependencies after recovery |
| TLS and DNS | Certificates, TLS private keys, chains, DNS and load balancer config | Clients/resource servers cannot connect securely |
| Deployment infrastructure | Images/versions, manifests, policies, networking, secret references, and runtime config | Cannot reproduce a consistent runtime environment |

In Spring Authorization Server, persistence abstractions such as **RegisteredClientRepository**, **OAuth2AuthorizationService**, and **OAuth2AuthorizationConsentService** represent distinct data groups. If using JDBC, back up the exact database/schema containing the corresponding tables. If using custom implementations, inventory every database, object store, or external system those implementations use.

Never place private keys, plaintext client secrets, database passwords, or KMS credentials inside a regular data backup bundle. Data backups and key backups require separate access controls, encryption, and recovery procedures. A backup is practically useful only when administrators still hold access to the decryption keys.

## 3. Designing a backup strategy

A strategy typically combines three layers:

1. **Scheduled backups**: take scheduled full backups, then incremental or differential backups to reduce storage and duration.
2. **Point-in-time recovery (PITR)**: retain transaction logs or write-ahead logs to restore the database to a specific timestamp before an error occurred.
3. **Isolated copies**: replicate backups to an independent region or storage account with immutability/object-lock policies to reduce the risk of encryption or deletion alongside production.

For relational databases, prefer the database engine's consistent backup mechanism. Merely copying a live data directory can yield an inconsistent snapshot unless coordinated with the database's snapshot/checkpoint mechanism. If the database is distributed or spans multiple schemas, define transaction boundaries and recovery ordering across components.

Each backup should include a manifest containing at minimum:

- Backup start and completion timestamps, timezone, and backup ID.
- Associated database/schema, environment, and application version.
- Recovery point or transaction log sequence to apply.
- Version of issuer configuration, RegisteredClient records, and token policies.
- Version/key ID of active signing keys and the list of corresponding public keys.
- Encryption status, storage location, checksum, and integrity verification results.
- Person or system creating the backup, outcome, and any warnings.

For signing keys, use backup/replication capabilities supported by your HSM or KMS. If private keys live in a keystore, protect the keystore file and its password using separate secrets management systems. Never store the decryption password alongside the backup file. For non-exportable HSM keys, the DR plan must rely on vendor backup/replication, standby hardware, or an approved replacement key generation procedure.

Apply the 3-2-1 rule where appropriate: keep multiple copies, store across at least two media types or fault domains, and keep at least one copy off-site/outside the production account. Off-site copies require independent access controls; the runtime account running the Authorization Server should never have permission to delete immutable backups.

## 4. Keeping the database and signing keys consistent

The Authorization Server issues tokens using signing keys and stores authorization/consent state in the data store. These two asset groups must be managed as a correlated recovery unit.

For example, suppose the database is restored to time T1 while the key store only retains a key created at T2. The server might still sign tokens, yet cannot reconstruct the key ID history, key status, or configuration active at T1. Conversely, restoring the database while losing an old private key can leave the system unable to continue signing with the old key or restore rotation configuration.

Store key metadata alongside configuration backups: **kid**, algorithm, key type, creation time, signing start time, signing stop time, current status, and key storage location. Private keys must be protected separately; public keys can be recorded in manifests for reconciliation and re-publication during recovery.

For every database recovery point, know:

- Which RegisteredClients existed at that point.
- Up to which transaction authorizations and consents were persisted.
- Which key was actively signing tokens at that point.
- Which public keys must continue being published to verify unexpired tokens.
- Which keys had already been revoked or untrusted.

Never assume restoring an older database automatically restores accurate token state. A snapshot may miss revocation actions that occurred after the snapshot timestamp. If a refresh token was revoked after the snapshot and the older backup is restored, old state can make that token appear unrevoked. Therefore, whenever recovery incurs lost transactions, assess the impact on tokens and consents before reopening endpoints.

## 5. Managing signing key lifecycle and rotation

Spring Authorization Server can use **JWKSource<SecurityContext>** to supply keys for JWT signing and publish the JWK Set at the corresponding endpoint. The system must maintain a controlled key ring instead of generating a new random key pair each time the application starts.

Each key requires a unique **kid** and an allowed algorithm. Private keys are used strictly for signing operations; corresponding public keys are published so resource servers and clients can verify signatures. When using KMS/HSM, the integration layer must ensure signing executes under the selected key and published JWKs match that key's public key.

Routine rotation procedure:

1. Generate a new key in KMS/HSM or a protected keystore; record **kid**, algorithm, and owner.
2. Verify the public key and JWK Set configuration. Publish the new public key before starting to sign with it so resource servers have time to fetch and cache it.
3. Switch the Authorization Server to sign new tokens with the new key; verify token headers carry the new **kid** and signatures validate cleanly.
4. Keep publishing the old public key for the duration needed to verify tokens previously issued with the old key.
5. Stop publishing the old public key only after all tokens signed with it have expired, plus clock skew, JWKS cache lifetimes, and an operational safety margin.
6. Archive or destroy the old private key per cryptographic policy and retain rotation evidence.

Never reuse a **kid** for a different key pair. Never remove the old public key immediately upon starting to sign with the new key, as resource servers may still need to verify still-valid tokens signed earlier.

If an old private key is suspected or confirmed compromised, the emergency procedure differs from routine rotation: trust in the affected key must be removed and tokens signed by it must be evaluated. Merely switching to a new key does not invalidate old JWTs if resource servers still trust the old public key.

## 6. Authorization Server recovery plan

DR runbooks should name the incident coordinator, database owner, key custodian, application operator, approver, and incident communication channels. General steps are as follows:

### Step 1: Confirm the incident and isolate scope

Identify whether the failure lies in instances, deployment region, database, KMS/HSM, certificates, or configuration. If intrusion or key compromise is suspected, restrict access and preserve logs, audit trails, snapshots, and relevant evidence. Do not delete resources or hastily rotate keys before recording the current state.

### Step 2: Select the recovery point

Choose the latest integrity-verified backup meeting the RPO. If PITR is required, determine the exact transaction logs to replay and the stop timestamp. Verify matching signing key backups, key ring metadata, required secrets, and issuer configuration.

If a backup might contain compromised data, do not restore it into production without assessment. When multiple backups exist, prefer a verified clean recovery point rather than blindly picking the newest one.

### Step 3: Restore infrastructure and data

Provision a recovery environment with network policies, secret access, and least-privilege permissions. Restore the database into an isolated environment first, run integrity checks, and verify schema/version compatibility with the application. Restore signing key access via HSM/KMS or a protected keystore; verify **kid**, algorithm, and public keys.

Restore issuer and endpoint configuration so the issuer URI does not change unexpectedly. Issued tokens contain the **iss** claim; if the post-recovery issuer differs from before, resource servers may reject tokens or OIDC metadata becomes inconsistent.

### Step 4: Start up and verify before accepting traffic

Start an instance in a verification environment, then confirm:

- Discovery metadata returns the right issuer and endpoints.
- The JWKS endpoint publishes required public keys with appropriate **kid** and algorithms.
- Registered clients load accurately with expected redirect URIs, grant types, and scopes.
- Authorization code flow, PKCE, token exchange, and refresh tokens operate per configuration.
- Existing consents read accurately.
- Introspection and revocation work if the system uses those endpoints.
- Audit events are recorded and linkable via correlation/trace IDs.
- System clocks are synchronized; TLS certificates, DNS, load balancers, and database/KMS connections are all valid.

Use controlled test accounts and clients, never placing real tokens into logs or test commands. Verify both happy paths and rejection cases. Open traffic only after the responsible owner confirms data and keys are accurate.

### Step 5: Shift traffic and monitor post-recovery

Shift traffic gradually if the architecture permits. Monitor error rates on the authorization endpoint, token endpoint, JWKS, introspection, and revocation; monitor database/KMS connection errors, response latencies, and refresh failure counts. Retain fallback capability to the DR region or old nodes until stability is confirmed and a formal decision is made.

Once the service is operational, take a fresh backup, verify scheduled backups resume running, and document any data loss window, actual recovery time, and follow-up improvements.

## 7. Handling consequences of delayed authorization database recovery

This area requires dedicated evaluation before reopening the service. JWT access tokens can be verified locally by resource servers via signatures and expiration without querying the Authorization Server's database. Consequently, restoring the database to an earlier state does not automatically invalidate already-issued JWTs.

However, the database holds critical state for subsequent operations:

- Refresh tokens may no longer match current rotation state.
- Tokens revoked after the backup point may lose their revocation record.
- New authorizations created after the snapshot may no longer exist.
- Newly granted or withdrawn consents may be lost.
- Introspection may return stale results if it relies on the authorization store.

Whenever there is risk of restoring stale state, do not merely verify the application boots and open traffic. Compare the snapshot timestamp against audit logs, transaction logs, or independent event sources to identify missing revocations and consent changes.

If full state cannot be reconstructed, operations must select appropriate risk mitigations, such as invalidating affected refresh tokens, requiring re-authentication, requesting consent again where necessary, or enforcing broad revocation policies. Bulk invalidation or global session checks usually must be designed at the application/resource-server layer; Spring Authorization Server does not provide a single built-in switch that instantly revokes all issued JWTs across every resource server.

Document the scope of affected tokens and clients, start/end timestamps, operational decisions, and user impact. Never claim JWTs are revoked merely because authorization records were deleted in the database: resource servers validating JWTs offline may continue accepting them until expiration unless another state-checking mechanism exists.

## 8. Signing key incident response runbook

Signing key incidents vary in severity. Distinguish losing the ability to use a key from losing the confidentiality of a key.

| Incident | Indicators | Priority action |
|---|---|---|
| KMS/HSM temporarily unreachable | Signing errors, timeouts, or permission errors | Switch to backup region/appliance per procedure; keep the same key and inspect KMS audit logs |
| Private key lost or unrecoverable | No longer able to sign with the active **kid** | Generate an approved replacement key, publish the new public key, and assess old tokens |
| Private key suspected compromised | Anomalous access, unauthorized export, or signs of forged JWTs | Isolate key, stop signing with it, preserve evidence, and trigger compromise workflow |
| Key confirmed compromised | Evidence external parties can use the private key | Remove trust in the affected public key and handle tokens signed with that key |
| Public key accidentally deleted from JWKS | Resource servers fail to verify valid tokens | Restore the proper public JWK and check resource server caches/refreshes |
| Key expired or algorithm no longer allowed | Signing/verification errors or policy rejections | Execute planned rotation, update algorithms, and check compatibility |

### When the key is only temporarily unreachable

1. Verify whether the error originates from KMS/HSM, network, policy, or credentials.
2. Inspect KMS/HSM audit logs and standby region health.
3. Fail over to a standby endpoint or appliance following vendor guidance.
4. Confirm the same **kid** and public key remain active before resuming token issuance.
5. Monitor signing errors and verify a test token using the matching public key.

Never automatically generate a new random key whenever KMS experiences a brief outage. If the application boots with an unmanaged new key, resource servers may not recognize that public key and newly issued tokens will fail verification.

### When a private key is lost

1. Identify which key was lost, which **kid** was active, and which tokens remain unexpired.
2. Check recoverability from verified HSM/KMS backups or keystore backups.
3. If unrecoverable, generate a new key under proper controls and approvals.
4. Publish the new public key before signing tokens with the new key.
5. Decide how to handle old tokens. If the old public key remains available and the key was not compromised, resource servers can keep verifying old tokens until expiration. If the old public key was also lost, assess recovering the public key from backups or planning user re-authentication.
6. Update manifests, backups, and key inventory.

Losing a private key does not mean the key was compromised. If confidentiality can be verified, keeping the old public key in JWKS until tokens expire minimizes disruption. If confidentiality cannot be proven, treat the event as a compromise incident.

### When a private key is compromised or suspected compromised

1. Activate the incident response workflow and record the earliest suspected time of compromise.
2. Isolate key usage permissions for the affected key in KMS/HSM; stop issuing tokens with it.
3. Generate a new key from a trusted source, switch to signing with the new **kid**, and publish the new public key.
4. Assess tokens signed by the compromised key, including access tokens, ID Tokens, and other tokens using the same key.
5. Remove the compromised public key from the trusted key set and instruct resource servers to refresh JWKS/caches via system mechanisms.
6. If resource servers might continue accepting tokens from stale caches, activate supplemental revocation controls: introspection, denylist, token version/session epoch, or re-authentication policies depending on architecture.
7. Audit KMS/HSM logs, access permissions, deployment pipelines, secret stores, and backups that may have held the affected key.
8. Notify dependent teams per incident procedure and record decisions, blast radius, and completion timestamps.

Removing a public key from JWKS does not guarantee every resource server immediately rejects tokens signed with that key. Resource servers may cache the JWK Set for some interval. Know cache TTLs, refresh mechanisms, forced reload capabilities, and have a plan when resource servers still retain the old public key.

Replacing a signing key also does not automatically revoke all token types identically. Already-issued JWTs may remain accepted by offline-verifying resource servers; opaque tokens may depend on introspection and authorization state. Runbooks must explicitly address each token type and resource server behavior.

## 9. Maintaining service during DR

Depending on RTO requirements, choose one of the following models:

| Model | Operation | Trade-off |
|---|---|---|
| Cold standby | DR environment is provisioned when an incident occurs | Lower cost, longer RTO |
| Warm standby | Infrastructure and partial data are pre-provisioned | Moderate RTO, requires periodic sync |
| Hot standby | Standby environment runs continuously with near-real-time data replication | Lower RTO, higher cost and complexity |

With hot standby, prevent split-brain. Never allow two independent Authorization Servers to write authorization state concurrently or issue tokens under divergent key rings without explicit synchronization and partitioning designs. Database replication lag can also drop recent revocations or refresh token rotations during a regional failover.

Keep the issuer stable between production and DR if both regions represent the same Authorization Server. Ensure DNS, TLS certificates, redirect URIs, network policies, and resource servers are all compatible with the post-failover endpoints. If forced to change the issuer, treat it as an architectural change requiring a dedicated migration plan for clients, resource servers, discovery metadata, and existing tokens.

## 10. Testing backups and conducting disaster recovery drills

A backup is considered reliable only after a tested restore. Testing schedules should include both automated checks and scenario-based drills.

| Test scenario | Pass criteria |
|---|---|
| Restore database from full backup | Schema and data readable; integrity checks pass |
| PITR to a specific timestamp | Data matches transaction logs and selected recovery point |
| Restore key access | KMS/HSM or keystore can execute test signing operations |
| Restore JWK Set | **kid**, algorithm, and public keys match previously issued tokens |
| Restore consents and clients | Registered clients and consents read accurately |
| Recover after losing a region | Endpoints, issuer, TLS, database, and keys work in the DR region |
| Restore an older snapshot | Missing revocations/refreshes/consents are identified and mitigation policy applied |
| Compromised key response | Affected key is no longer used for signing and resource servers reject tokens per policy |
| Failback traffic | No split-brain or unsynchronized dual-region writes occur |

After every drill, measure actual RPO and RTO and compare them against agreed targets. Record detection time, decision time, database restore time, key recovery time, verification time, and time to reopen traffic. These measurements pinpoint real bottlenecks.

## 11. Periodic operational checklist

- [ ] Database backups and transaction logs run on schedule; alerts fire on job failures.
- [ ] Off-site backups are encrypted, immutable, and checksummed.
- [ ] Backup access permissions are separated from the Authorization Server's runtime permissions.
- [ ] Signing keys have an inventory listing **kid**, algorithm, status, owner, and expiration.
- [ ] KMS/HSM has redundancy and recovery permissions have been tested.
- [ ] Backup decryption secrets are stored independently with access controls.
- [ ] Old public keys remain published long enough for token lifetimes and JWKS caches.
- [ ] Issuer, discovery metadata, DNS, and TLS certificates are configuration-managed with assigned owners.
- [ ] Database restores, key recovery, and regional failovers are rehearsed on schedule.
- [ ] Runbooks name on-call responders, approvers, communication channels, and traffic-reopening criteria.
- [ ] Audit trails capture backup, restore, key rotation, and key access operations.
- [ ] After every restore, assess the risk of tokens revoked or consents changed after the backup point.

An Authorization Server's backup and disaster recovery plan is complete only when it can simultaneously restore data, key usage rights, and token-issuing configuration, and then prove OAuth 2.0/OIDC flows still work properly. Regular drills help operations teams uncover gaps early between a backup job succeeding on paper and actual service recoverability.
