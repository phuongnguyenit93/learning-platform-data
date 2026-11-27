# Encryption in Transit, at Rest, and Decryption Access Management

> **Chapter:** Security Architecture  
> **Module:** CLOUD_ARCHITECTURE  
> **Scope:** Designing cloud application architectures from business requirements through networking, compute, data, and deployment model choices; balancing reliability, security, scalability, cost, and operations using Well-Architected thinking.

## Learning Objectives

After this lesson, you can:

1. Distinguish encryption in transit, encryption at rest, and application/field-level encryption.
2. Design TLS for clients, service-to-service, databases, queues, and management connections; identify TLS termination points and trust boundaries.
3. Explain the roles of certificates, trust chains, private keys, CAs, mTLS, and certificate lifecycles.
4. Describe envelope encryption, DEKs, KEKs, KMS/HSM, and how to protect data in databases, object storage, and backups.
5. Design separate key permissions for encrypt/decrypt, separate operational roles, and enforce access control by workload/tenant.
6. Plan key creation, storage, distribution, rotation, revocation, backup, and destruction; analyze impact on historical data.
7. Identify risks in secrets, logs, caches, replicas, snapshots, and data copies.
8. Verify designs via policy reviews, certificate/key rotation drills, access tests, and restore tests.

## 1. Why Does Cloud Architecture Need Encryption?

Cloud applications transmit data across many boundaries: browser to gateway, gateway to service, service to database, producer to broker, worker to storage, and data replicated to other regions. Data also exists in many forms: memory, temporary files, objects, database tables, snapshots, logs, caches, and backups.

Encryption reduces the likelihood of data being read if an attacker eavesdrops on the network, gains unauthorized access to storage, or steals a copy. However, encryption **does not authenticate users by itself, grant permissions by itself, stop a valid application from reading the wrong tenant's data, or protect plaintext once decrypted inside a process**.

A design must answer three questions:

- **Where is data protected?** On the network, in storage, in backups, in sensitive fields, or during processing?
- **Who can decrypt?** Which workload identity, role, service account, or human is allowed to use the key?
- **Who controls the key?** Who creates, rotates, disables, revokes, recovers, and destroys the key?

### 1.1. Three Common Protection Layers

| Layer | Objective | Examples |
|---|---|---|
| **Encryption in transit** | Protect data moving across networks | TLS between browser and API, mTLS between two services |
| **Encryption at rest** | Protect data stored on media | Database encryption, object storage encryption, encrypted backups |
| **Application/field-level encryption** | Protect values from storage layers or broader access groups | Encrypting government ID numbers before writing to the database |

These layers complement each other. TLS does not protect files once written; disk encryption does not stop a valid database role from querying data; field encryption does not replace record-level read authorization.

### 1.2. Boundaries and Limitations

Suppose a client calls the Booking API, which writes to a database, emits an event, and stores backups:

- TLS can protect client → gateway and gateway → API.
- Database connections should be encrypted and authenticate the server; client certificates can be added if the platform supports them and the threat model warrants it.
- Databases/storage encrypt at rest using service-managed or organization-controlled keys.
- Backups and replicas must fall under the same encryption, retention, and access policies.
- Fields containing PII can be encrypted before writing, though search/indexing and key management must be designed accordingly.
- Logs/traces must mask sensitive data; encrypting logs does not fix overly broad log-read permissions.

When an application must process data, plaintext typically appears in memory or at the decrypting endpoint. If data must also be protected during processing, evaluate other techniques such as confidential computing/TEEs, tokenization, or computing over transformed data; each has its own scope and limitations.

## 2. Encryption in Transit: TLS and Connection Authentication

### 2.1. What Does TLS Protect?

TLS (Transport Layer Security) establishes a cryptographically protected channel between two endpoints. Properly configured, TLS provides:

- **Confidentiality:** third parties along the path cannot easily read contents.
- **Integrity:** detects tampering with data in transit.
- **Server authentication:** the client verifies the server via certificate and hostname.
- **Optional client authentication:** with mutual TLS, the server also verifies the client's certificate.

TLS does not verify which booking a user is allowed to place, does not automatically prevent business-layer replay, and does not protect plaintext after TLS terminates. Applications still require authentication, authorization, rate limiting, input validation, and auditing.

### 2.2. TLS Termination and Hops

A request may pass through multiple TLS termination points:

~~~mermaid
flowchart LR
    C[Browser / Mobile] ==>|TLS| EDGE[CDN / WAF / Load Balancer]
    EDGE ==>|TLS or mTLS| GW[API Gateway]
    GW ==>|TLS or mTLS| APP[Booking Service]
    APP ==>|TLS| DB[(Database)]
    APP ==>|TLS| MQ[Message Broker]
~~~

Each segment is a separate encrypted channel. When a CDN/load balancer terminates TLS, plaintext may exist inside that component; re-encrypting on the next hop creates a new channel rather than one end-to-end TLS session.

Determine:

- Where does TLS terminate and which components can see plaintext?
- Are backend hops required to use TLS or can the gateway call plain HTTP internally?
- Who issues and renews certificates for each listener/service?
- How are hostname/SNI and hostname verification enforced?
- Are headers representing client identity safely regenerated/overwritten by the gateway?
- Do proxy logs record sensitive headers, bodies, or tokens?

Never treat a private network as a reason to drop TLS between services. In the cloud, internal traffic can still traverse shared infrastructure, service meshes, proxies, or separate administrative domains.

### 2.3. Choosing TLS Versions and Configuration

Prefer supported TLS versions and configure cipher suites/algorithms according to current platform and organizational security standards. For modern Internet services, TLS 1.2 and TLS 1.3 are typically the versions to consider; restrict legacy protocols such as SSL and TLS 1.0/1.1 under an evaluated compatibility policy.

Principles:

- Disable weak protocols/ciphers and obsolete algorithms.
- Use valid certificate chains, matching hostnames/SANs, and managed trust stores.
- Enable hostname verification; never ignore certificate errors in production.
- Choose session resumption and 0-RTT according to application semantics; avoid replay-prone mechanisms on state-changing requests without analysis.
- Monitor certificate expiry, handshake failures, active TLS versions, and negotiated ciphers.
- Audit configurations on edges, gateways, services, databases, brokers, and admin endpoints—not just public websites.

Exact configurations must follow provider recommendations, runtime libraries, compliance, and client support. Never copy outdated cipher lists into production without verification.

### 2.4. Server Certificates and Trust Chains

Servers present certificates to prove identity. Clients verify:

1. The certificate is signed by a CA in the trust store or chains to a trusted anchor.
2. The certificate's validity period is current.
3. Hostname/SAN matches the target name the client is connecting to.
4. Key usage/extended key usage fits the server authentication role.
5. The certificate has not been revoked under the applicable check mechanism (OCSP/CRL or another policy).

Public certificates can be distributed widely; **accompanying private keys must be strictly protected**. Never commit private keys to Git, container images, frontend bundles, tickets, or logs. Keep private keys in a secret manager, HSM, or protected key store; grant access per workload and rotate if exposure is possible.

### 2.5. Mutual TLS (mTLS)

In mTLS, both client and server present certificates to authenticate identity at the transport layer. This is a strong option for service-to-service, workload-to-database, or partner integrations needing PKI-bound workload identities.

~~~mermaid
sequenceDiagram
    participant A as Service A
    participant B as Service B
    A->>B: ClientHello
    B-->>A: Server certificate + proof
    A->>A: Verify server chain and hostname
    B-->>A: Request client certificate
    A-->>B: Client certificate + proof
    B->>B: Verify client chain, identity and policy
    A->>B: Encrypted application request
    B-->>A: Encrypted response
~~~

mTLS strengthens connection identity assurance but does not replace authorization. Service B must still verify which operations Service A may call and which tenants/resources it may access. Map certificate identities to principals/roles using explicit policies.

### 2.6. Certificate Lifecycle

A sound lifecycle includes:

- **Issue:** verify workload/hostname identity and issue certificates from an approved CA.
- **Distribute:** deliver via secret/certificate manager or workload agent; restrict private key export.
- **Install:** update listener/client trust stores without baking keys into images or source.
- **Renew/rotate:** auto-renew ahead of expiry, supporting overlap between old and new certificates.
- **Revoke:** revoke upon key exposure, workload compromise, or invalid identity.
- **Audit/retire:** retain metadata and history; purge private key copies per procedure.

Measure days remaining before expiry, renewal failures, handshake failures, and unrotated certificates. A renewed certificate that a service fails to reload can still expire in production.

## 3. Encryption at Rest: Storage, Databases, and Backups

### 3.1. Encryption at Rest

Encryption at rest protects data stored on media/object/block/file storage via service or application encryption mechanisms. Managed implementations typically encrypt blocks/objects/database pages with a data key and protect that data key via a key management service.

Cover:

- Primary databases, replicas, read replicas, snapshots, and automated backups.
- Object storage, object versions, replication destinations, and archive tiers.
- Block volumes, file shares, persistent disks, and container volumes.
- Queue/broker storage, dead-letter queues, and message archives if present.
- Search indexes, cache persistence, analytics extracts, and temporary staging.
- Logs, traces, crash dumps, and artifacts that may hold sensitive data.

Never infer that every copy is automatically encrypted just because primary storage has encryption enabled. Check each backup type, export, cross-region copy, and downstream service.

### 3.2. Server-Side Encryption vs. Client-Side Encryption

| Approach | Where Encryption/Decryption Occurs | Benefits | Limitations |
|---|---|---|---|
| **Server-side encryption (SSE)** | Storage/database service | Seamless integration, minimal app changes | Service still decrypts for authorized workloads; does not hide plaintext from the service |
| **Client-side/application encryption** | App encrypts before sending to storage and decrypts after reading | Can prevent storage services from seeing plaintext | App manages keys, rotation, search, and added compatibility complexity |
| **Volume/disk encryption** | Block/device layer | Covers files/pages on offline media | Does not replace app, transport, or database permission controls |
| **Field-level encryption** | Sensitive fields only | Shrinks plaintext exposure and enables split permissions | Querying/indexing/sorting is harder; requires dedicated tokenization/search designs |

SSE usually serves as the baseline encryption at rest for managed services. When the threat model requires preventing database operators or storage exports from reading certain fields, consider client/field-level encryption or tokenization; define who holds keys and which applications may decrypt.

### 3.3. Encryption Scope and Plaintext

~~~mermaid
flowchart TB
    APP[Application] -->|TLS + encrypted payload| DB[(Encrypted Database)]
    DB --> SNAP[(Encrypted Snapshot / Backup)]
    DB --> REP[(Encrypted Replica)]
    APP -->|TLS| OBJ[(Encrypted Object Storage)]
    APP --> LOG[Log / Trace Pipeline]
    LOG --> MASK[Redaction / Data minimization]
    MASK --> STORE[(Encrypted Log Storage)]
    KEY[KMS / HSM] -. key operations .-> APP
    KEY -. protects data keys .-> DB
    KEY -. protects data keys .-> OBJ
~~~

This diagram illustrates protection layers; concrete implementations may use provider-managed keys without the app calling KMS directly. Logs must minimize plaintext upfront. If an app writes tokens/emails to logs and then encrypts log storage, authorized log readers can still view that sensitive data.

## 4. Key Management and Envelope Encryption

### 4.1. Why Not Use One Master Key for All Data?

A single key with overly broad scope creates a huge blast radius. If that key leaks or is revoked, all dependent data is affected. Encrypting large volumes directly under one key also complicates rotation, access scoping, throughput, and auditing.

**Envelope encryption** uses at least two key layers:

- **Data Encryption Key (DEK):** the data key encrypting an object, record, file, or data group.
- **Key Encryption Key (KEK):** the higher-level key used to encrypt (wrap) DEKs; typically managed inside KMS/HSM.

Flow:

1. The application asks KMS to generate a DEK or generates a DEK with an approved CSPRNG workflow.
2. The plaintext DEK encrypts data in memory using authenticated encryption.
3. The application sends the DEK to KMS for wrapping, or receives both plaintext DEK and wrapped DEK from the service API.
4. Store ciphertext alongside wrapped DEK, nonce/IV, algorithm/version, and required metadata.
5. On read, an authorized workload asks KMS to unwrap the DEK, decrypts data in memory, and clears the plaintext key from working memory when feasible.

### 4.2. Envelope Encryption Diagram

~~~mermaid
sequenceDiagram
    participant App as Application
    participant KMS as KMS / HSM
    participant Store as Data Storage
    App->>KMS: Generate or request data key
    KMS-->>App: Plaintext DEK + wrapped DEK
    App->>App: Encrypt data with DEK (AEAD)
    App->>Store: Ciphertext + wrapped DEK + nonce + metadata
    Note over Store: Plaintext DEK is not stored
    Store-->>App: Ciphertext + wrapped DEK + metadata
    App->>KMS: Unwrap DEK (authorized workload identity)
    KMS-->>App: Plaintext DEK
    App->>App: Authenticate and decrypt ciphertext
~~~

Not every KMS API returns a plaintext DEK in the same way; some services offer direct encrypt/decrypt APIs or dedicated data-key caching. Always follow your provider's official SDK/API and semantics.

### 4.3. Encrypted Data Attributes

| Attribute | Purpose |
|---|---|
| `encrypted_data` | Ciphertext payload |
| `wrapped_dek` | DEK encrypted by the KEK |
| `key_id`/`key_version` | Identifies the wrapping key or version |
| `algorithm` | Cryptographic algorithm/suite and version |
| `nonce`/`IV` | Unique parameter required by the encryption mode |
| `authentication_tag` | Authentication tag when using AEAD |
| `schema`/`version` | Plaintext structure and decryption rules |
| `associated_data` | Non-secret metadata bound to ciphertext to authenticate context |

Never reuse a nonce in violation of algorithm/mode requirements. For AES-GCM, nonce/IV uniqueness per key must stay within implementation limits; uncontrolled random generation can create collision risk at high volumes. Use vetted crypto libraries—never invent primitives.

Authenticated encryption (AEAD), such as AES-GCM or ChaCha20-Poly1305 where supported, provides both confidentiality and integrity. Never use unauthenticated encryption for sensitive payloads without proper MAC/integrity verification.

### 4.4. DEK Scope

DEKs can be scoped:

- Per object/file: small failure scope, more key metadata to manage.
- Per record/field: stronger isolation, higher overhead and harder querying.
- Per tenant: simplifies tenant isolation and per-customer destruction/rotation, though large datasets may need multiple DEKs/versions.
- Per batch/dataset: fewer KMS calls, larger blast radius for cached plaintext keys.

Choose scope based on volume, risk, deletion/rotation requirements, and throughput. Document where wrapped DEKs and key IDs are stored, cache lifetimes, and rewrap procedures.

## 5. KMS, HSM, and Key Hierarchies

### 5.1. Role of KMS

A Key Management Service (KMS) provides APIs and a control plane to create, store, protect, use, rotate, disable, and audit keys. KMS usually eliminates running your own HSM/key servers while still requiring sound policies and permissions.

A key record may contain:

- Key ID/resource identifier and alias.
- Algorithm/key type and usage (encrypt/decrypt, sign/verify, wrap).
- Key state: enabled, disabled, pending deletion/destroyed.
- Region/account/project, owner, and rotation policy.
- Key policies/IAM grants and audit events.
- Metadata linking to workloads, data classification, and business owner.

KMS keys are not secrets applications should download for direct local use. In many models, cryptographic operations run inside the key service or via data-key APIs; asymmetric private keys may be non-exportable.

### 5.2. HSM

A Hardware Security Module (HSM) is dedicated hardware or a hardware-backed service protecting cryptographic operations and key material in a controlled boundary. An HSM may be needed when:

- Compliance mandates specific protection levels or control forms.
- Non-exportable keys, hardware auditing, or dual control are required.
- Workloads require specialized crypto operations or predictable throughput.
- The organization requires tighter control over key lifecycles/infrastructure.

HSMs increase cost and demand operational rigor across backup/replication, availability, client libraries, and governance. Never assume an HSM makes the whole system secure if apps still log plaintext or roles can request decryption arbitrarily.

### 5.3. Key Hierarchy

~~~mermaid
flowchart TB
    ROOT[Root / HSM protected boundary]
    ROOT --> KEK1[KEK: Production data]
    ROOT --> KEK2[KEK: Backup vault]
    ROOT --> KEK3[KEK: Tenant / domain scope]
    KEK1 --> D1[Wrapped DEKs: Database objects]
    KEK1 --> D2[Wrapped DEKs: Object data]
    KEK2 --> D3[Wrapped DEKs: Backup sets]
    KEK3 --> D4[Wrapped DEKs: Sensitive fields]
~~~

This diagram illustrates a logical hierarchy. Concrete deployments may use cloud-managed root keys, customer-managed keys, per-environment keys, or provider-specific hierarchies. Avoid building custom root-key hierarchies outside evaluated protections and backup procedures.

### 5.4. Provider-Managed vs. Customer-Managed Keys

| Type | Description | Trade-Offs |
|---|---|---|
| Provider-managed key | Provider creates/operates keys and rotates per service | Less toil; policy/rotation control varies by service |
| Customer-managed key (CMK) | Customer controls policies, disabling, rotation, or deletion as supported | Stronger control/auditing; policy/key-state mistakes can lock apps out |
| Customer-provided key | Customer supplies key material per supported service model | High material control; greater storage, backup, rotation, and operational responsibility |

Terminology and semantics vary across providers. Review key ownership, exportability, rotation, regional scope, backup, and deletion behavior carefully. Do not confuse a customer-managed key with application-implemented field-level encryption.

## 6. Decryption Access: Who Can Use Keys and on Which Data?

### 6.1. Separating Data Usage from Key Administration

Distinguish these permissions:

- **Encrypt/generate data key:** produce new ciphertexts or DEKs.
- **Decrypt/unwrap:** obtain plaintext or unwrap DEKs to read data.
- **Re-encrypt/rewrap:** rewrap DEKs under another KEK without decrypting payloads where supported.
- **Manage key policy:** modify key permissions or configuration.
- **Rotate:** create new key versions/material per service mechanisms.
- **Disable/revoke/delete:** suspend or destroy a key.
- **Audit/read metadata:** inspect key history and state.

Runtime applications may need to decrypt booking data without permission to disable/delete the KEK. Security teams may manage key policies without permission to read business data. Separation of duties prevents a single leaked credential from both reading data and destroying keys.

### 6.2. Sample Permission Matrix

| Principal | Encrypt/Generate | Decrypt/Unwrap | Manage Policy | Disable/Delete | Audit |
|---|---:|---:|---:|---:|---:|
| Booking API runtime | Yes, within booking scope | Yes, authorized booking data | No | No | No |
| Analytics workload | Possibly no | Only granted curated datasets | No | No | No |
| Backup service | Yes/rewrap per policy | Approved restore scope | No | No | Metadata |
| Security key admin | Per procedure | Not by default | Yes | Under dual control | Yes |
| Auditor | No | No | No | No | Read-only |
| Break-glass operator | Temporary per incident | Approved scope only | Time-bound | May require dual approval | Yes |

This table is a template for separation of duties; some KMS engines combine actions or scope policies per key/service. Check your platform's exact authorization model.

### 6.3. Workload Identity Policy

~~~text
Principal: booking-api-production
Allowed actions:
  - GenerateDataKey
  - Decrypt
Resource:
  - booking-production-key
Conditions:
  - environment == production
  - workload identity == booking-api
  - encryption context tenant_scope == assigned scope
Denied:
  - DisableKey
  - ScheduleKeyDeletion
  - PutKeyPolicy
~~~

This is pseudocode policy, not native syntax for any cloud provider. In real policies, use exact resource IDs, supported conditions, and test with real principals. Encryption context/AAD binds ciphertext to context but does not replace application-level authorization.

### 6.4. Tenant Isolation and Support Access

For multi-tenant systems:

- Use per-tenant keys or a domain key with per-tenant DEKs; choose based on compliance, cost, and scale.
- Bind key/DEK metadata to tenants using authenticated context; never trust client-supplied tenant IDs.
- Prevent tenant A from passing tenant B's ciphertext or wrapped DEK by altering IDs.
- Support access must require approval, time limits, auditing, and a clear purpose.
- When offboarding a tenant, determine whether deleting data keys achieves cryptographic erasure or if plaintext/backups/caches remain elsewhere.

**Cryptographic erasure** is only effective if all related copies become undecryptable with no surviving keys or key copies. Deleting a key in KMS does not erase exported plaintext, cached DEKs, replicas, or backups encrypted under another key.

## 7. Key Rotation, Re-Encryption, and Revocation

### 7.1. Rotation Does Not Always Require Re-Encrypting All Data

With envelope encryption, KEKs can rotate in two ways:

- Create a new KEK version and **rewrap DEKs** from the old key to the new key. Data ciphertexts stay untouched if DEKs remain unchanged.
- Generate new DEKs and **re-encrypt data**. This requires reading ciphertexts, decrypting with old DEKs, and re-encrypting under new DEKs.

Rewrapping requires much less I/O because only wrapped DEKs/metadata are processed, but is only appropriate when the threat model allows keeping old DEKs. If a DEK is suspected exposed, merely rewrapping it does not negate an attacker who already holds the plaintext key; generate new DEKs and re-encrypt the affected data.

### 7.2. Reference Rotation Workflow

1. Identify dependent keys, workloads, datasets, backups, and consumers.
2. Create the new key version or new key; configure policies and auditing.
3. Grant workloads access to the new key; test encrypt/decrypt in staging.
4. Switch new writes to the new key version.
5. Rewrap DEKs or re-encrypt data in planned, controlled batches.
6. Verify migrated record/object ratios, decryption checks, and error rates.
7. Keep the old key in decrypt-only state during the migration/retention window as needed.
8. Confirm no remaining data or backups depend on the old key before disabling/revoking.
9. Monitor applications, restore paths, and audits; update inventory/runbooks.

Never disable an old key the moment the write path switches to a new key. Old snapshots, replicas, archives, backups, and un-backfilled records may still require the old key for months.

### 7.3. Rotation, Disabling, and Deletion Are Distinct

| Action | Meaning | Risk |
|---|---|---|
| Rotation | Creates new key material/version per policy; behavior depends on KMS | Legacy clients or historical data need compatibility |
| Disable | Halts certain key operations | Apps/restores may fail to decrypt |
| Revoke access | Removes principal permissions | Can break workloads if dependencies have not migrated |
| Schedule deletion | Schedules key destruction per service waiting period | Irreversible destruction once the waiting period ends |
| Destroy material | Destroys key material per mechanism | Protected data may become permanently undecryptable |

Do not hit disable/delete as a reflex on suspected credential exposure before assessing impact. During an incident, you may need to revoke principals, rotate secrets/certificates, and selectively disable keys while preserving clean data recovery.

### 7.4. Key Compromise Response

When a key or private key is suspected compromised:

- Determine key type, exposure window, principals, and potentially affected data.
- Block/revoke compromised access and credentials.
- Determine whether the attacker could call decrypt APIs or extracted plaintext key material.
- Provision new keys inside a cleaned trust boundary.
- Re-encrypt data if key material/DEKs could be exposed; simple rewrapping may be insufficient.
- Consider certificate revocation, session/token invalidation, and rotating related credentials.
- Inspect KMS, storage, database, export logs, and anomalous decrypt volumes.
- Restore from clean backups if data was tampered/deleted while preserving forensic evidence.
- Notify customers/regulators per incident procedures and reporting obligations.

## 8. Protecting Keys, Secrets, and Configurations

### 8.1. Distinguishing Keys, Certificates, and Application Secrets

| Type | Role | Examples |
|---|---|---|
| Encryption key | Encrypts/decrypts data | DEK, KEK, database key |
| Signing key | Signs and verifies signatures | Private key signing JWTs or artifacts |
| TLS private key | Proves endpoint identity in TLS | Private key of a server/client certificate |
| Password/API secret | Authenticates to external services | DB password, API token |
| Certificate | Carries public key and CA-signed identity metadata | X.509 certificate |

Do not dump everything into one shared config file. Secret managers, KMS, and certificate managers serve different functions; pick the right service and restrict permissions.

### 8.2. Where Keys Must Never Live

- Source code, Git history, pull requests, and issue trackers.
- Frontend/mobile bundles if it is a secret key; any secret shipped to clients can be extracted.
- Docker images, package artifacts, build caches, or test fixtures.
- Logs, traces, crash dumps, telemetry attributes, and shell history.
- Unencrypted backup files or broadly readable temp directories.
- Chats/emails/tickets or publicly shared documents.

If a secret was ever committed, deleting the line in the latest commit is not enough: history, forks, caches, and artifacts may still hold it. Treat the key as exposed, rotate/revoke it, and purge copies per policy.

### 8.3. Runtime Secret Retrieval

Applications should fetch secrets/keys via workload identity and a secret manager with minimal scope. Decide:

- Fetch at startup or on demand; refresh upon rotation.
- How long to cache secrets/keys in memory.
- Behavior when KMS/secret manager is temporarily unavailable.
- How to avoid logging plaintext in exception traces.
- Who can impersonate the workload identity.
- How to revoke credentials if a pod/VM is compromised.

Caching reduces latency and KMS dependency, yet widens the window an attacker can use a cached key if a process is compromised. Bound cache lifetimes to rotation, revocation, and threat model; never cache plaintext keys indefinitely.

## 9. Application-Layer and Field-Level Encryption

### 9.1. When Is an Extra Encryption Layer Needed?

Provider volume/database encryption generally protects media and snapshots against physical theft or unauthorized storage paths. However, organizations sometimes need to limit plaintext visibility for:

- Database administrators or storage operators.
- Analytics workloads permitted to view only certain fields.
- Multiple services sharing a database where not all should see PII.
- Exports or objects that might be shared with third parties.

Field-level encryption encrypts values before persistence. However, it complicates equality/range/sort queries because ciphertexts do not preserve ordering or deterministic equality by default.

### 9.2. Field Encryption Example

~~~text
Input:
  customer_id = opaque identifier
  national_id = plaintext-sensitive-value

Application:
  DEK = data key scoped to approved domain/tenant
  ciphertext, nonce, tag = AEAD_Encrypt(DEK, value, associated_data)
  wrapped_DEK = KMS_Wrap(KEK, DEK)

Persist:
  customer_id
  encrypted_national_id
  nonce
  authentication_tag
  wrapped_DEK
  key_id + schema_version
~~~

On read, the application authenticates the principal and tenant, retrieves the wrapped DEK, calls KMS unwrap, verifies the authentication tag/AAD, and decrypts in memory. If the tag is invalid, treat it as tampered data or mismatched key/metadata; never return plaintext or ignore authentication failures.

### 9.3. Searching Encrypted Data

Randomized encryption produces different ciphertexts for identical plaintexts, reducing pattern leakage while preventing direct equality lookups. Alternatives include:

- **Tokenization:** replace sensitive values with reference tokens managed by a dedicated vault/service.
- **Blind index/HMAC token:** compute a deterministic lookup value using a separate key, stored apart from ciphertext.
- **Deterministic encryption:** identical plaintexts produce identical ciphertexts within a scope; supports equality but leaks frequency/patterns.
- **Privileged search service:** decrypt inside a controlled service or query through a dedicated API.

Each option carries different leakage trade-offs. Blind indexes/HMAC tokens still reveal duplicates, frequencies, and enable correlation; lookup keys must be separate from encryption keys with separate policies. Never use unkeyed hashes for predictable value spaces like phone numbers, emails, or IDs.

### 9.4. Data Requiring Sorting or Range Queries

Standard encryption does not preserve order, making `BETWEEN` queries, amount sorting, or date ranges non-trivial. Avoid homegrown order-preserving encryption without rigorous leakage analysis. Usually it is better to filter on non-sensitive or coarsened fields, use tokenization, partition services, or process inside an authorized environment.

## 10. Data Copies: Backups, Replicas, Logs, Caches, and Exports

Encryption policies must follow data throughout its entire lifecycle:

| Location | Common Risk | Controls |
|---|---|---|
| Primary DB | Overly broad read roles; query exports | DB roles, network, encryption, auditing |
| Read replica | Creates additional PII copies | Inherit keys/policies, restrict consumers |
| Snapshot/PITR | Wrong backup key/retention | Backup vault, KMS policies, restore drills |
| Object version/replica | Old versions linger after deletion | Lifecycle rules, inventory, deletion workflows |
| Queue/DLQ | Sensitive payloads linger long | Payload minimization, encryption, retention, restricted access |
| Cache | Plaintext in memory/persistence | Network isolation, TTL, encryption if supported, access control |
| Log/trace | Tokens/PII accidentally logged | Source redaction, sampling, roles, and retention |
| Export/CSV | Downloaded files leave control plane | Short-lived URLs, encryption, watermarking/auditing, expiry |
| Temporary files | Plaintext files on worker volumes | Ephemeral encrypted storage, cleanup, restricted processes |

Storage encryption does not replace data minimization. The surest way to avoid exposing a piece of data is not collecting or copying it unless business needs require it.

## 11. Integrity, Authenticity, and Key Usage

### 11.1. Encryption Is Not Signing

- **Encryption** prevents parties without the key from reading contents.
- **Message Authentication Code (MAC)** confirms data was not altered by someone lacking the secret key.
- **Digital signature** proves data was signed by the holder of the private signing key, verified with the public key.

AEAD typically combines confidentiality and integrity for ciphertexts. Digital signatures fit scenarios needing origin verification of artifacts, documents, or messages across multiple systems. Never use plain encryption alone as proof of sender identity.

### 11.2. Signing Keys and Rotation

For signed tokens/JWTs or artifacts, consumers may need old public keys to verify tokens/artifacts issued prior to rotation. Therefore include:

- Key ID/version in headers/metadata.
- Overlap windows for old/new public keys.
- Token lifetimes and revoke/deny policies.
- Procedures to revoke compromised private keys.
- Never confuse signing keys with encryption KEKs.

Using one key for multiple purposes lets an issue in one protocol compromise another. Separate keys by purpose and algorithm/domain following the key separation principle.

### 11.3. Auditing Key Usage

Audits must answer:

- Which principal called encrypt/decrypt/unwrap?
- What were the timestamp, key ID, region/account, and context?
- Which workload/tenant did the request belong to?
- Were there anomalous decrypt volumes, unusual source locations, or off-hours calls?
- Who changed key policies, rotation, disabling, or deletion schedules?

Never write plaintext, raw keys, tokens, or PII-laden encryption contexts into audit logs. Log request IDs, principal IDs, and minimal metadata for investigation; protect logs against tampering/deletion and restrict read access.

## 12. Performance, Availability, and Cost of Key Operations

### 12.1. KMS Is a Runtime Dependency

If every request calls KMS repeatedly, KMS latency and quotas can impact APIs. If KMS or network connectivity to KMS fails, workloads may fail to decrypt data.

Options:

- Use envelope encryption to shrink payloads sent to KMS; KMS only wraps/unwraps DEKs.
- Cache DEKs with bounded lifetime and narrow scope when policy allows.
- Bound KMS call rates and apply retries with backoff/jitter and deadlines.
- Pre-warm or provision data keys for batch jobs safely.
- Monitor KMS throttling, latency, availability, and decrypt failures.
- Never retry infinitely or fall back to plaintext when KMS fails.

Caching plaintext DEKs reduces runtime dependency but extends how long an attacker can use the key if a process is compromised. Constrain TTLs, memory access, process isolation, and zeroize keys upon completion where supported by the runtime.

### 12.2. Retries and Availability

KMS errors include permission denied, throttling, timeouts, invalid ciphertext, disabled keys, or service outages:

- Permission/configuration errors: retries will not help; alert immediately.
- Throttling/transient network errors: retry with backoff, jitter, deadlines, and caps.
- Invalid ciphertext/tag: do not retry blindly; likely corruption or tampering.
- Disabled/deleted keys: invoke key recovery/incident workflows; never bypass with unauthorized keys.

Never fall back to plaintext or hardcoded keys to preserve availability. Key recoverability and decryption access are part of DR; restore tests must prove keys work in recovery regions/accounts.

### 12.3. Cost

Encryption TCO includes KMS/HSM keys and encrypt/decrypt/wrap requests; certificate authorities, issuance/renewal, and secret managers; storage overhead for nonces, tags, wrapped DEKs, metadata, and versions; compute CPU and crypto latency; backup/replica keys, multi-region HSMs, and audit logs; plus operational labor for access reviews, rotations, and incident drills.

Optimize cost through envelope encryption, well-sized DEK scopes, minimizing data encrypted at the app layer, bounded caching, and metadata lifecycle hygiene—never by dropping auditing, backups, or isolation just to shave a KMS fee.

## 13. Security Architecture Design Process

1. **Data inventory:** types, classifications, volumes, flows, owners, and retention.
2. **Threat model:** who can eavesdrop, read storage, steal credentials, tamper with data, or take over KMS?
3. **Map data flows and trust boundaries:** TLS termination points, storage, replicas, backups, logs, and exports.
4. **Select baseline encryption:** TLS for all relevant hops; at-rest for storage/backups; field-level/tokenization where required.
5. **Choose key hierarchy:** provider-managed/customer-managed, KEK/DEK scope, KMS/HSM, and regions.
6. **Design access policies:** workload identities, encrypt/decrypt, admin/audit, separation of duties, and tenant context.
7. **Define lifecycle:** issue, distribute, cache, rotate, rewrap, revoke, recover, and destroy.
8. **Stress-test workloads:** latency, quotas, concurrency, KMS failover, restores, certificate renewals, and key compromise.
9. **Operationalize:** dashboards, alerts, inventory, audits, runbooks, and periodic reviews.

### 13.1. Sample Data Flow Inventory

| Data Flow | Classification | Transport Protection | At-Rest Protection | Principals Able to Decrypt |
|---|---|---|---|---|
| Browser → API | Confidential | TLS + server auth | Not stored at edge or minimized in logs | API runtime after authentication |
| API → Booking DB | Confidential/PII | TLS, optionally mTLS | DB encryption, backup encryption | Booking DB role + workload |
| API → Event broker | Internal/minimal PII | TLS/mTLS | Broker storage encryption | Approved consumers |
| DB → Backup vault | Confidential/PII | Service private channel/TLS | Dedicated backup key or verified policy | Recovery role |
| Worker → Email provider | Confidential | TLS | Managed secrets/tokens; logs omit sensitive contents | Specific worker scope |
| Analytics → Curated lake | Confidential or de-identified | TLS | Object/table encryption | Approved analytics identity |

The matrix must reflect actual flows. If a gateway terminates TLS and calls a backend in plaintext, the transport column must say so; never mark an entire flow as TLS simply because the client leg is encrypted.

### 13.2. Sample Key Inventory

| Attribute | Values to Manage |
|---|---|
| `key_id` / `alias` | Non-secret key identifier |
| `purpose` | Encryption, wrapping, signing, or TLS |
| `scope` | Environment, domain, tenant, or dataset |
| `owner` | Accountable team |
| `key policy` | Principal/action/resource/conditions |
| `lifecycle` | Created, enabled, rotation, expiry, deletion |
| `dependencies` | Databases, objects, backups, services, and versions |
| `recovery` | Backups/replicas, decrypt rights, and recovery procedures |
| `audit` | Log location, alert owner, and retention |

Inventories must never contain key material, secrets, or private keys.

## 14. Testing and Drills

### 14.1. Testing TLS and Certificates

| Test | Purpose | Criterion |
|---|---|---|
| Hostname mismatch | Catch server identity misconfiguration | Client rejects handshake |
| Expired/untrusted certificate | Check trust/expiry enforcement | Connection rejected and alert fires |
| Invalid mTLS client | Verify workload identity checks | Server blocks request before app logic |
| Backend hop | Verify TLS after termination | No unapproved plaintext hops |
| Rotation overlap | Renew without downtime | Old and new clients succeed during window |
| Revocation | Halt compromised certificate | New connections rejected per policy |

### 14.2. Testing KMS and Encryption at Rest

- Write new data and confirm ciphertext/wrapped DEK are persisted properly.
- Decrypt with a valid workload identity.
- Attempt access with an unauthorized principal; must deny and audit.
- Disable a key in a test environment; verify workloads fail safely without falling back to plaintext.
- Rotate KEK and verify old/new data remain readable during overlap.
- Rewrap/re-encrypt in batches and reconcile record/object counts.
- Restore backups into a recovery environment and verify keys/permissions work.
- Simulate KMS throttling/network outages; verify retries, timeouts, and alerts.

### 14.3. Testing Field Encryption and Data Leakage

- Randomized encryption produces changing ciphertexts for identical plaintexts as expected.
- Tag/AAD mismatches cause decryption to fail.
- Tenant A cannot decrypt Tenant B's ciphertexts.
- Logs, exceptions, traces, and crash dumps contain no plaintext/keys.
- Exports, caches, and temp files obey policy.
- Old keys remain managed while restores require them; destruction occurs only after retention expires with approval.

### 14.4. Rotation and Incident Drills

1. Rotate certificates for a group of services, watching handshakes and error rates.
2. Rotate a KEK, rewrap DEKs, and verify old/new records.
3. Simulate a compromised principal, revoke rights, and issue a fresh identity.
4. Restore backups in another region using DR key policies and permissions.
5. Measure execution time and missing dependencies; update runbooks.

Never rehearse disabling/deleting production keys without approvals, blast-radius assessment, backups, recovery paths, and stop conditions. Use dedicated test keys/datasets for destructive tests.

## 15. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Enabling HTTPS only at the edge | Backend hops may transmit plaintext | Encrypt every hop across trust boundaries |
| Disabling hostname verification | TLS is present yet clients can connect to wrong servers | Verify hostname, chain, and trust store |
| Using mTLS without authorization | Valid services reach disallowed operations/tenants | Map identity to roles and policies |
| Granting app runtimes KEK admin/delete rights | Compromised app credentials can destroy both data and keys | Separate encrypt/decrypt from admin/delete |
| Encrypting volumes and assuming PII is safe everywhere | Logs/exports/caches/replicas still hold plaintext | Inventory full data lifecycle, minimize, and protect copies |
| Hardcoding keys in apps/images/Git | Keys get extracted and persist in history | KMS/secret manager, rotate, and remediate leaks |
| Rotating keys and immediately deleting old keys | Old backups/records become undecryptable | Dependency inventory, overlap, and restore tests |
| Rewrapping an exposed DEK and calling it fixed | Attackers may already hold the plaintext DEK | Re-encrypt with new DEKs per incident scope |
| Using one key for all purposes/tenants | Huge blast radius, hard to audit | Separate by purpose/scope and policy |
| Omitting decryption metadata | Ciphertext unrecoverable even with the key | Store key ID/version, nonce, tag, and schema version |
| Logging plaintext then encrypting log storage | Authorized log readers still see PII | Redact/minimize before writing |
| Caching plaintext DEKs indefinitely | Process compromise allows long-term reads | Bound TTL/scope, memory hygiene, and revocation plans |
| Treating encryption as authorization | Valid callers read cross-tenant data | AuthN, authZ, tenant isolation, and auditing |
| Never restore-testing with keys in the DR region | Backups exist but cannot be decrypted | End-to-end drills including KMS/IAM/network |

## 16. Hands-On Exercise: Designing Encryption for a Booking Platform

**Scenario:** A booking platform includes Web/Mobile clients, an API Gateway, Booking Service, a relational database, an event broker, object storage, and an analytics lake. Data includes bookings, email/phone numbers, payment references, and attached documents. The system runs across two regions; some enterprise tenants require dedicated key control. The Booking API requires low latency; operations must be able to restore data during DR.

Design the following:

1. **Data classification:** classify public/internal/confidential/PII data; identify fields that do not need storing and where copies exist.
2. **TLS map:** diagram client → gateway → service → DB/broker/storage; mark termination, TLS/mTLS, server/client identities, and trust boundaries.
3. **Certificate lifecycle:** define CA, issuance, private key storage, rotation, overlap, revocation, expiry alerts, and owners.
4. **At-rest baseline:** specify encryption for databases, replicas, snapshots, objects, queues, backups, logs, and analytics.
5. **Field encryption:** select fields needing app-level encryption/tokenization; explain impacts on search, indexing, sorting, and analytics.
6. **Key hierarchy:** design KEK/DEK, key scopes by environment/domain/tenant, KMS/HSM, and required metadata.
7. **Authorization:** build a principal/action/resource matrix; separate workload decryption from security admins and break-glass access.
8. **Rotation/recovery:** describe KEK rotation, rewrapping/re-encryption, key compromise, and preserving restore capability for old backups.
9. **Observability:** KMS latency/throttle/decrypt-failure metrics, certificate expiry/handshakes, auditing, and anomaly alerts.
10. **Testing:** test tenant isolation, unauthorized principals, TLS hostname mismatch, certificate rotation, key rotation, KMS outages, and DR restores.
11. **Well-Architected:** document trade-offs across security, reliability, performance, cost, operations, and sustainability.

### Sample Decision Table

| Flow/Data | In-Transit Protection | At-Rest Protection | Decryption Access | Evidence |
|---|---|---|---|---|
| Web/Mobile → Gateway | TLS, hostname verification | Sensitive request bodies omitted from edge logs | Gateway/API per identity | TLS scan, log tests |
| Gateway → Booking API | TLS or mTLS | Managed runtime secrets | Booking workload | Backend hop test, IAM |
| Booking API → DB | TLS, DB server identity | DB/backup encryption | Booking DB role/workload | Connection test, restores |
| Booking API → Broker | TLS/mTLS | Broker storage encryption | Approved consumers | ACL/decrypt tests |
| PII fields in DB | TLS in DB flow | Field AEAD + wrapped DEK as needed | Granted service/domain | Tenant isolation, tag/AAD tests |
| Backups to Region B | Service TLS/private replication | Dedicated backup vault key or verified policy | DR recovery role | Cross-region restore drill |
| Analytics lake | TLS | Object/table encryption, masking | Analytics identity | Access review, PII scan |

**Completion criteria:** A reviewer can trace sensitive data from ingestion to deletion, understand how every hop is encrypted, who controls keys, which principals can decrypt, and how to recover when keys/certificates fail or are compromised. Unverified provider assumptions must be flagged for testing.

## 17. Well-Architected Evaluation

| Pillar | Encryption and Key Management Questions | Evidence |
|---|---|---|
| **Operational Excellence** | Do certificates/keys have inventories, owners, automated rotation, alerts, and runbooks? | Rotation drills, expiry dashboards, key inventory |
| **Security** | Is TLS proper, key scope narrow, least privilege enforced, audited, and data minimized? | TLS tests, IAM policy tests, audit reviews, leakage scans |
| **Reliability** | Do KMS/keys have HA/recovery, are backups decryptable, and are rotations outage-free? | Restore drills, key recovery, failure tests |
| **Performance Efficiency** | Do crypto/KMS latency, throughput, and caching meet load demands? | p95 decrypt, KMS throttles, load tests |
| **Cost Optimization** | Are key counts, KMS calls, HSMs, logs, and storage overhead justified? | KMS cost/showback, DEK scope reviews |
| **Sustainability** | Are redundant data copies, keys/versions, and unnecessary crypto compute minimized? | Data lifecycle, utilization, retention reviews |

Strong encryption is not merely picking a strong algorithm. It combines authenticated transport channels, protected storage, governed key lifecycles and permissions, minimized plaintext, and verified recoverability.

## 18. Summary Framework

- **In transit:** protect every hop with TLS; verify certificates/hostnames and use mTLS when mutual workload authentication is needed.
- **At rest:** cover databases, objects, replicas, snapshots, backups, queues, logs, and exports; inspect every copy.
- **Envelope encryption:** DEKs encrypt data, KEK/KMS protects DEKs; persist sufficient metadata for decryption.
- **Key authorization:** separate encrypt/decrypt permissions from policy changes, disabling, or deletion; apply workload identity and least privilege.
- **Planned rotation:** distinguish rotate, rewrap, re-encrypt, revoke, and delete; retain old keys as long as backups/records need them.
- **Field-level encryption trade-offs:** reduces plaintext exposure while impacting search, sorting, indexing, and analytics.
- **End-to-end verification:** certificate renewals, key rotations, unauthorized decryption, backup restores, KMS outages, and incident response.

A trustworthy encryption architecture protects data from the wire to backups while strictly bounding who can decrypt and who administers keys. Every choice must factor in data lifecycles, performance, and recoverability: ciphertext is only useful when keys are protected, permissions are properly scoped, metadata stays intact, and the organization can legitimately decrypt when needed.
