# 32.10. Backup, Retention, and Protection of Authorized Client Data

A **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client** application may have HTTPS, PKCE, `state`, and ID Token signature verification configured correctly and still suffer a serious security incident if an **access token** or **refresh token** sits in a database, backup, log, or storage area lacking proper controls.

In Spring Security, an `OAuth2AuthorizedClient` binds a **client registration**, a **principal**, and the issued **OAuth2 tokens**. If the application retains these objects across HTTP requests or restarts, they must be managed as **credential-bearing assets**, not an ordinary cache table.

This lesson belongs to chapter **32. Deployment and Operations**, focusing on three capabilities:

1. **Backup and restore:** does authorized client data need to be backed up, what should be backed up, where, how is it encrypted, and how is it restored and verified?
2. **Retention and deletion:** how long should tokens be retained; how should user logout, consent revocation, tenant offboarding, expired tokens, data in backups, and data deletion requests be handled?
3. **Protection at rest and in operations:** encryption, authorization/permissions, key management, user/tenant isolation, avoiding token leakage, handling refresh token rotation, and post-restore incidents.

Examples use **Spring Boot 3.x, Spring Security 6.x (referencing the 6.5 API), Java 17+, and PostgreSQL** when explaining durable storage. Illustrative configurations and SQL are not a complete encryption system or retention policy that can be used verbatim in production.

> **Key takeaway:** **Successfully restoring a row in the database does not mean successfully restoring the OAuth2 session.** A refresh token in a backup may already have been rotated, revoked, or expired at the Authorization Server. The system must **fail closed**, delete invalid credentials, and start a new authorization flow when needed; do not force the Authorization Server to accept an old token.

---

## 1. Distinguishing Authorized Client from Other Objects

These concepts have similar names but different lifecycles and risks.

| Component | What does it contain? | Does it contain a credential usable to call APIs? | Typical lifecycle |
| --- | --- | --- | --- |
| `ClientRegistration` | `registrationId`, `clientId`, provider endpoints, scope, grant, and possibly `clientSecret` | **May contain client secret**, but not user access tokens | Configuration/secrets lifecycle |
| **`OAuth2AuthorizedClient`** | Registration + principal name + access token + optional refresh token | **Yes** | Until expiration, revocation, deletion, or reauthorization |
| `OAuth2AuthorizationRequest` | `state`, redirect URI, PKCE verifier, OIDC nonce context | Contains sensitive login transaction data, not an authorized-client token cache | Short-lived authorization redirect/callback |
| `SecurityContext` | `Authentication`, principal, and authorities | May reference identity, but is not by default an authorized client token store | HTTP/session lifetime |
| `OAuth2AuthorizedClientService` | API to load/save/remove authorized clients at the application level | Manages data containing tokens | According to the storage implementation |
| `OAuth2AuthorizedClientRepository` | API to load/save/remove authorized clients across web requests | May involve session/service persistence | According to HTTP/session |
| Authorization Server | Token issuance, consent, grant status, revocation | Yes | According to AS policy |

In Spring Security, `OAuth2AuthorizedClient` contains at least:

```text
OAuth2AuthorizedClient
  clientRegistration
    registrationId = company-login
    clientId = portal-client
    provider/issuer = https://id.example.test/...
  principalName = principal-key-123
  accessToken
    tokenValue = <secret>
    tokenType = Bearer
    issuedAt / expiresAt
    scopes = [profile.read]
  refreshToken (optional)
    tokenValue = <high-value-secret>
    issuedAt
```

**Do not print this object via `toString()`, do not serialize the entire object into a JSON response, and do not arbitrarily store it in audit events.** Token data inside the object is a secret even if it is labeled a “cache”.

### 1.1. Authorized Client Is Not ClientRegistration

A `ClientRegistration` can be recreated from configuration and a secret manager. `OAuth2AuthorizedClient` contains tokens **issued by the AS** for a specific registration/principal.

If you only back up the authorized clients table but lose the corresponding `ClientRegistration`:
- The app may not recognize the registration ID;
- The token endpoint/issuer/client ID may have changed;
- Cache records may no longer match the current configuration.

Conversely, backing up configuration while omitting authorized clients may require users to log in/consent again, without necessarily losing business data. This opens the option of **not backing up tokens** in some architectures.

### 1.2. Authorized Client Is Not Authorization Request

`OAuth2AuthorizationRequest` is stored **while waiting for the callback**; it contains state/PKCE/nonce context. Losing this request causes a callback correlation failure, not authorized-client storage corruption.

Do not apply multi-month retention to `OAuth2AuthorizationRequest`. Redirect transactions need a short TTL and one-time consumption.

### 1.3. A Record Can Represent a User or a Service Account

| Grant | Principal of authorized client | Who is the token issued for? |
| --- | --- | --- |
| `authorization_code` | Usually a user principal | Permissions delegated by the user/AS to the client |
| `client_credentials` | Should use a stable service principal name | Permissions of the application/service identity |
| `refresh_token` | Attached to an already issued authorized client | Renews tokens under the existing grant/policy |

Therefore, backup/retention policies must distinguish between **user-delegated tokens** and **machine-to-machine tokens**. A service token can be re-acquired automatically; a user token may require interaction and new consent.

---

## 2. Why Is Authorized Client Data Particularly Sensitive?

### 2.1. An Access Token Is an Immediately Usable Credential

With a Bearer token, anyone holding a still-valid token can attempt to use it at a Resource Server matching the audience/scope. TLS protection in transit does not help if the token was leaked from a database backup.

### 2.2. A Refresh Token Can Carry Prolonged Risk

A refresh token allows the client to request new access tokens and typically has a longer lifetime than an access token. Depending on the AS, a refresh token has:
- Absolute expiration;
- Inactivity timeout;
- Rotation on every use;
- Reuse detection;
- Binding to client/device/certificate;
- Revocation by user or administrator.

In particular, **a backup containing refresh tokens can become a reusable copy of credentials**, even if the primary database has already been protected or the record was deleted.

### 2.3. Principal Name Can Be Personal Data

`principalName` may be:
- OIDC `sub`;
- Internal username;
- Email if the system is configured that way;
- Service account ID.

Emails and identifiers used to correlate with a user can still be personal data. The table can reveal **which provider is connected to which person** even if the token value is encrypted.

### 2.4. Tokens Can Reveal Information Through Their Contents

A JWT access token typically contains `iss`, `sub`, `aud`, `scope`, expiry, and possibly business claims. JWT is **Base64URL-encoded**, not confidentially encrypted by default. A backup containing plaintext JWTs can also expose claims.

### 2.5. Sensitive Assets Do Not Live Only in the Token Column

Data can spread to:
- Database snapshots;
- WAL/binlog and replication;
- Redis persistence files;
- Object storage backups;
- Cloud backup vaults;
- Traces/APM/heap dumps;
- Debug HTTP logging;
- Error reports, crash dumps;
- Support tickets;
- Developer database exports;
- CI artifacts;
- Search indexes;
- Local laptop copies.

Enabling encryption on a single table alone does not protect copies in other layers.

---

## 3. Threat Model: Who Can Access This Data?

| Actor / Scenario | Goal | Defense layer |
| --- | --- | --- |
| Compromised database read-only account | Read access/refresh tokens | Least privilege, token field encryption, audit |
| Accidentally shared backup object | Download snapshots containing credentials | Isolated backup IAM, SSE, retention, access logs |
| Stolen KMS key | Decrypt snapshots or ciphertext | Key access boundaries, rotation, per-scope keys |
| Compromised application pod | Read in-use tokens | Workload identity, containment, minimal egress |
| Dev exports production DB to staging | Expose tokens in weaker environment | Do not copy live tokens; sanitization |
| Support staff prints record | Use debug tool to view raw tokens | RBAC, redaction, break-glass, approvals |
| Restoring backup from a prior day | Use an already-rotated refresh token | Freeze/reconcile, invalid_grant handling |
| Tenant A queries Tenant B token | Cross-tenant credential access | Strong tenant key + repository authorization |
| Concurrent refresh from two replicas | Use same refresh token / rotation race | Locking/CAS, versioning, idempotent strategy |
| User revokes consent | Client still stores old token | Local deletion + AS revocation when possible |
| Data deleted but snapshot remains | Recovery brings deleted token back | Deletion ledger/tombstone replay, backup expiry |
| Credential rotation | Restored record linked to old client secret | Secret/key version lifecycle |

**Principle:** protecting authorized client data requires **confidentiality**, **integrity**, **availability**, and **deletion correctness**. A single encryption mechanism only solves part of the problem.

---

## 4. Storage Options in Spring Security

### 4.1. OAuth2AuthorizedClientService

Service-level API:

```java
public interface OAuth2AuthorizedClientService {
    <T extends OAuth2AuthorizedClient> T loadAuthorizedClient(
        String clientRegistrationId, String principalName);

    void saveAuthorizedClient(
        OAuth2AuthorizedClient authorizedClient,
        Authentication principal);

    void removeAuthorizedClient(
        String clientRegistrationId, String principalName);
}
```

This is a **simplified signature for explanation**, not a verbatim copy from a specific version. It illustrates all three behaviors: **load, save, remove**.

Common implementations:

- **`InMemoryOAuth2AuthorizedClientService`:** stores in-process, convenient for demos/tests, loses data on restart.
- **`JdbcOAuth2AuthorizedClientService`:** stores in a relational database via JDBC using the Spring Security schema.
- **Custom OAuth2AuthorizedClientService:** uses custom storage and/or application-level encryption; must preserve the contract.

### 4.2. OAuth2AuthorizedClientRepository

`OAuth2AuthorizedClientRepository` handles authorized clients across **Servlet web requests**. Common implementations like `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` may delegate to `OAuth2AuthorizedClientService` for authenticated principals and use a session-level repository for certain anonymous cases.

**Do not conclude “tokens only live in HttpSession” or “all tokens live in JDBC” without inspecting the application's actual repository/service wiring.**

### 4.3. DefaultOAuth2AuthorizedClientManager and Service Manager

| Context | Appropriate Manager |
| --- | --- |
| Servlet HTTP request | `DefaultOAuth2AuthorizedClientManager` with `OAuth2AuthorizedClientRepository` |
| Scheduled/background/service-tier code | `AuthorizedClientServiceOAuth2AuthorizedClientManager` with `OAuth2AuthorizedClientService` |
| Reactive WebFlux HTTP | `DefaultReactiveOAuth2AuthorizedClientManager` |
| Reactive background/service tier | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` |

Success/failure handlers on the manager can save or remove authorized clients based on token issuance/refresh results. **Understand this behavior before designing backup or restore**, because an `invalid_grant` can cause the currently saved record to be removed.

### 4.4. Token Cache Is Not Shared Across Instances by Default

`InMemoryOAuth2AuthorizedClientService` in pod A does not share tokens with pod B. If authorized clients must survive restarts/failover, shared persistence or an appropriate reauthorization strategy must be used.

**A shared database does not automatically solve concurrent refresh token rotation.** It only makes records visible; update atomicity still has to be designed.

---

## 5. First Decision: Do Token Values Need to Be Backed Up?

A common architectural mistake is **backing up every table out of habit** and only then trying to figure out how to protect the tokens. Ask first: **If the entire authorized-client cache is lost, can the system recover via reauthorization?**

### 5.1. Option A — Do Not Back Up Token Values

Appropriate when:
- `client_credentials` can automatically request new tokens;
- Users can log in/consent again at an acceptable cost;
- Losing cached tokens does not lose irreproducible business data;
- Reducing credentials in backups takes priority over seamless recovery.

```text
Database loss
    -> authorized-client cache empty
    -> machine client requests new token
    -> browser user logs in/authorizes again when needed
    -> business data in separate storage is still restored
```

Pros: reduces exposure surface in snapshots and avoids restoring stale refresh tokens.

Cons:
- Users may have to log in/consent again;
- The AS may experience increased load after disaster recovery;
- Background workflows need warm-up/retry plans;
- OP/AS unavailability during recovery can prolong downtime.

**If you choose to omit tokens from backups**, ensure the backup/export process genuinely excludes them and does not inadvertently retain tokens in WAL, replica snapshots, or another table.

### 5.2. Option B — Back Up Encrypted Authorized Clients

Appropriate when:
- Reauthorizing many users causes major disruption;
- Integrations need to keep refresh tokens for an allowed duration;
- Key management and controlled restore mechanisms are in place;
- The risks of stale/rotated/revoked tokens have been evaluated.

```text
Active DB --encrypted backup--> Isolated backup vault
      |                                 |
      |                                 v
      |                           Controlled restore
      |                                 |
      v                                 v
App keeps using tokens              Reconcile validity
                                    / purge stale entries
                                       |
                                       v
                                 Controlled resume
```

**Note:** a successful backup does not mean restored tokens are usable. Refresh token rotation can make restoring from an old snapshot **more dangerous than leaving the cache empty**.

### 5.3. Option C — Hybrid

For example:
- Do not back up machine access tokens;
- Back up encrypted user-delegated refresh tokens if needed;
- Back up `registrationId` metadata and pseudonymous principal keys;
- Separate the lifecycle/deletion ledger from the token table;
- Delete old tokens on restore if already revoked/expired.

A hybrid architecture needs to **clearly define authoritative data**. Do not let a token table restore overwrite “permission revoked” in the business system.

---

## 6. Designing a Backup Policy with RPO and RTO

**RPO (Recovery Point Objective)** is the acceptable amount of data loss measured in time. **RTO (Recovery Time Objective)** is the time required to restore the service.

For authorized-client tokens, RPO should not be mechanically copied from order or payment transaction tables.

| Data type | Example RPO/RTO considerations | Rationale |
| --- | --- | --- |
| Business orders/transactions | Very low RPO | Data loss cannot be recreated |
| Machine access-token cache | Losing entire cache may be acceptable | Tokens can be re-acquired via client_credentials |
| User authorized-client records | Depends on UX, re-consent frequency, and AS | Record loss may force reauthorization |
| Revocation/deletion ledger | Very low RPO or durable event log | Deleted credentials must never be “resurrected” |
| Encryption key metadata | Must stay consistent with retained backups | Key loss renders ciphertext unrecoverable |
| Token access audit events | According to security/compliance policy | Incident investigation and deletion proof |

**Illustrative examples**, not mandatory values:
- Critical application data: RPO of a few minutes;
- Authorized-client cache: RPO of several hours or intentionally not restored;
- Revocation/delete events: must be replayed up to every restore point;
- Token service RTO: sufficient to retry/reauthorize without overwhelming the AS.

Do not judge backup success merely by “the job runs every 24 hours.” You must verify **that restore works, uses the right key version, and does not resurrect deleted data**.

### 6.1. Full Backup, Incremental, and PITR

For databases:
- **Full snapshot:** periodic full copy;
- **Incremental/differential:** changes since the appropriate checkpoint;
- **WAL/PITR:** point-in-time recovery logs;
- **Replica:** serves availability, **not an independent backup** when data corruption or deletions are replicated.

All of these can contain plaintext tokens if the storage layer is unencrypted or data is exported in clear form.

### 6.2. Backup Isolation

Backups should live in a separate security boundary:
- Different credentials/roles from the primary app;
- Application accounts lack permissions to arbitrarily delete/read the backup vault;
- Encryption keys and IAM are scoped by least privilege;
- Object versioning/immutability where appropriate;
- Access logging and alerts on bulk downloads;
- Do not copy production backups to personal laptops or uncontrolled staging environments.

### 6.3. Verifying Backup Integrity

Beyond encryption, integrity mechanisms are needed:
- Artifact checksums/hashes;
- Authenticated encryption/signatures at the data layer;
- Immutable manifest of snapshot/LSN/time;
- Controlled restore rehearsals.

**Plain checksums do not authenticate the source or stop an attacker from modifying data and recomputing a new checksum.** Against a threat model involving backup tampering, authenticated integrity and proper permissions are required.

---

## 7. Retention: What to Keep and for How Long?

There is no single number that applies to every project or jurisdiction. Decisions must be based on:
- AS token lifetime and grant policy;
- User consent/revocation;
- Business needs;
- Threat model and sensitivity;
- Security/industry standards;
- Applicable legal/regulatory obligations;
- Backup schedule;
- SLAs and operational cost.

### 7.1. Suggested Retention Matrix for Discussion

| Data | When should it be kept? | Events requiring deletion/revocation | Notes |
| --- | --- | --- | --- |
| Active access token | While the authorized client is still in use | Grant revoked, user unlinked, cache invalidation | Access token expiresAt does not guarantee refresh token expiration |
| Active refresh token | While delegated authorization must continue and remains allowed | Logout per policy, unlink, consent revoke, inactivity, tenant offboard | High-sensitivity value |
| Machine client access token | While unexpired, saving token requests | Service decommission, credential revoke, policy change | Usually regenerable |
| Expired access token **without refresh token** | Can be deleted shortly after expiration/buffer | TTL cleanup | Check usage/races before deleting |
| Authorized client with refresh token | Until no longer permitted/needed | Revocation/expiry/inactivity policy | Do not rely solely on access token expiry |
| Pending authorization request | Short-lived wait for callback | Callback complete/timeout/error | Must not share authorized-client record retention |
| Access audit event | According to security/incident policy | Audit retention expiry | Do not record token values |
| Backup containing token data | According to specific disaster-recovery policy | Backup retention expiry, security incident | May require crypto-erasure |
| Key versions | While ciphertext/backups needing decryption remain | When no valid dependent data remains | Do not delete key early if restore is still required |
| Revocation/deletion tombstones | Long enough to cover all restore points | After no backup can resurrect the data | Should be stored separately without raw tokens |

**Milestones like 7/30/90 days in a given policy are only meaningful once approved.** Do not treat those durations as Spring Security defaults or confirmed legal mandates.

### 7.2. Access Token expiresAt Is Not Record Retention

An authorized client may contain:

```text
access_token.expires_at = 2026-11-16T10:00Z
refresh_token            = still valid until revoked/inactive timeout
```

If a cleanup job deletes the row right at 10:00Z solely because the access token expired, the application loses a valid refresh token, forcing unnecessary user re-consent.

Conversely, if there is no refresh token and the access token has expired, keeping the record indefinitely usually brings no operational benefit.

### 7.3. Refresh Tokens Do Not Always Have expiresAt

In Spring Security's model, `OAuth2RefreshToken` has `issuedAt` and may carry other information depending on the implementation/API, but the default JDBC schema **does not store an explicit `refresh_token_expires_at`**.

Do not fabricate a refresh token expiry using:
- `access_token_expires_at`;
- `created_at + 30 days` without an AS policy;
- An inferred JWT `exp` when the refresh token is opaque.

Have **separate lifecycle metadata** if the application must enforce inactivity/retention policies accurately.

### 7.4. Deleting Local Storage Differs from Revoking at the AS

`removeAuthorizedClient(...)` only deletes the record **on the client side**. It does not automatically:
- Revoke issued access tokens;
- Revoke refresh tokens on the AS;
- Clear the OP's SSO session;
- End all browser sessions;
- Delete copies in backups.

If policy requires revoking the grant, integrate with the AS **token revocation endpoint (RFC 7009)** when supported, with proper client authentication and result/timeout handling.

---

## 8. Configuring JDBC Persistence for OAuth2AuthorizedClientService

Spring Security 6.5 provides `JdbcOAuth2AuthorizedClientService` backed by `JdbcOperations`.

### 8.1. Dependencies

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-client</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

The Spring Boot BOM typically manages versions for these dependencies. This lesson does not run builds or modify project build files.

### 8.2. Original Spring Security JDBC Schema

Spring Security reference schema:

```sql
CREATE TABLE oauth2_authorized_client (
    client_registration_id varchar(100) NOT NULL,
    principal_name varchar(200) NOT NULL,
    access_token_type varchar(100) NOT NULL,
    access_token_value blob NOT NULL,
    access_token_issued_at timestamp NOT NULL,
    access_token_expires_at timestamp NOT NULL,
    access_token_scopes varchar(1000) DEFAULT NULL,
    refresh_token_value blob DEFAULT NULL,
    refresh_token_issued_at timestamp DEFAULT NULL,
    created_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
    PRIMARY KEY (client_registration_id, principal_name)
);
```

This is a **generic reference schema**; `BLOB` and timestamp types must be adapted to the database dialect. For PostgreSQL, binary fields typically use `BYTEA` and timestamps need a consistent timezone policy.

**Do not add `tenant_id` or change the default table's primary key and assume `JdbcOAuth2AuthorizedClientService` will automatically read/write the new columns.** This class uses SQL queries and row/parameter mappers tied to its own schema. If you design a different schema, custom persistence/mappers with clear migrations are required.

### 8.3. Creating the JDBC Service Bean

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.security.oauth2.client.JdbcOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
class AuthorizedClientStorageConfiguration {

    @Bean
    OAuth2AuthorizedClientService authorizedClientService(
            JdbcOperations jdbc,
            ClientRegistrationRepository registrations) {

        return new JdbcOAuth2AuthorizedClientService(
            jdbc, registrations);
    }
}
```

You need to:
- Run migrations to create the table matching the exact schema;
- Verify the application's database user has least-privilege permissions;
- Confirm Spring Boot selects this bean instead of in-memory storage;
- Enable TLS/authentication on the DB connection;
- Test save/load/remove with synthetic tokens in a test environment.

### 8.4. Example application.yml — Without Real Secrets

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal.example.test:5432/portal
    username: portal_oauth_client
    password: ${DB_PASSWORD}

  security:
    oauth2:
      client:
        registration:
          reports-machine:
            provider: company-as
            client-id: ${REPORTS_CLIENT_ID}
            client-secret: ${REPORTS_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope: [reports.read]
        provider:
          company-as:
            token-uri: https://auth.example.test/oauth2/token
```

`JdbcOAuth2AuthorizedClientService` does not auto-create tables in production just because the bean exists. Use Flyway/Liquibase or managed migrations. Never store `DB_PASSWORD` and `REPORTS_CLIENT_SECRET` in plaintext in git.

### 8.5. Does JDBC Encrypt Token Values by Default?

**Do not assume application-level encryption is enabled.** The schema uses binary columns to store token bytes; BLOB/BYTEA does not mean ciphertext. Database storage encryption/TDE and backup encryption are **separate layers**.

If your threat model requires that users with `SELECT` table permissions cannot see token values, you need **application-level token encryption** or a reviewed equivalent mechanism.

---

## 9. Encryption at Rest: Protecting Three Distinct Layers

| Layer | Protects against | Does not sufficiently protect against |
| --- | --- | --- |
| Disk/volume encryption | Physical disk snapshot theft | DBA/SQL role reading plaintext columns |
| Database TDE/storage encryption | Data files/physical backups depending on system | Application or DB account with SELECT privilege |
| Backup object encryption | Backup object theft without key | Backup account that also has decrypt permissions |
| **Application-level token encryption** | SQL reader/snapshot without application key | App pod compromised with both data and key |
| TLS DB/HTTP | Transit eavesdropping | Endpoint or backup compromise |
| IAM/least privilege | Unauthorized role-based access | Key/token leak from logs or app bugs |

**Defense layers must overlap.** Application-level encryption does not replace backup IAM; backup encryption does not replace access control on the active table.

### 9.1. What Is Envelope Encryption?

Commonly used flow:
1. Generate or retrieve a **Data Encryption Key (DEK)**.
2. Encrypt the token value using AEAD such as **AES-GCM** (or an equivalent reviewed algorithm).
3. Encrypt/wrap the DEK with a **Key Encryption Key (KEK)** managed in KMS/HSM.
4. Store ciphertext, authentication tag, nonce/IV, key version, or wrapped DEK.
5. On load, the authorized app uses KMS/key policy to decrypt; plaintext tokens exist in memory only where needed.

```text
Token plaintext
       |
       v
AEAD encryption with DEK + unique nonce + AAD
       |
       v
token_ciphertext + nonce + key_version / wrapped_DEK
       |
       v
Database / encrypted backups

Key lifecycle:
  KMS KEK ----wrap/unwrap----> DEK
       |
       +-- policies, audit, rotation, disable/destroy
```

### 9.2. Why Is Authenticated Encryption Needed?

Encryption is not only for hiding tokens. If an attacker modifies ciphertext, the system must **detect tampering**, rather than feeding corrupted/unauthenticated bytes into a security-critical flow.

With AES-GCM:
- Nonce/IV must be unique per key; never reuse;
- Authentication tag must be verified;
- Use a CSPRNG;
- Do not invent custom cryptographic formats;
- Do not store encryption keys in the same table as the ciphertext;
- Use a versioned format to upgrade algorithms/keys.

**Never use Base64, hashing, or Java serialization as “token encryption.”** Base64 can be decoded; one-way hashes cannot recover the token to call APIs.

### 9.3. Associated Authenticated Data (AAD)

AAD binds ciphertext to trusted metadata, for example:

```text
AAD = version=1
    | registrationId=company-login
    | principalKey=principal-key-123
    | tokenKind=refresh
    | tenantId=tenant-a
```

If an attacker copies Tenant A's ciphertext into Tenant B's row, decryption must fail due to an AAD mismatch.

Notes:
- AAD must be canonicalized consistently;
- Do not depend on a mutable raw email;
- Tenant/issuer boundaries must be part of the security design;
- If the principal key changes during migration, a re-encryption plan is needed.

### 9.4. Separating Token Types in Encryption

A row may contain both an access token and a refresh token. Never reuse the same **AEAD nonce** for two values under the same key; either generate a separate nonce per encryption or encrypt a clearly structured envelope.

An illustrative metadata format:

```json
{
  "format_version": 1,
  "key_version": "oauth-token-key-v4",
  "access_token_ciphertext": "<binary/base64-encoded-ciphertext>",
  "access_token_nonce": "<unique-random-nonce>",
  "refresh_token_ciphertext": "<binary/base64-encoded-ciphertext>",
  "refresh_token_nonce": "<another-unique-random-nonce>"
}
```

The strings above are placeholders, not real encrypted values.

### 9.5. Key Separation by Environment

- Never use the same DEK/KEK for production and staging;
- Never restore production token ciphertext into staging and grant a staging KMS key access to decrypt it;
- Scope KMS decrypt permissions to workload identity;
- Alert on abnormal decrypt volume;
- During incident response, have procedures to disable/rotate keys and revoke tokens.

**Losing a key can make all authorized clients unrecoverable on restore.** This may be an acceptable choice if policy permits reauthorization, but it must be anticipated rather than treated as a surprise outage.

---

## 10. Designing an Encryption Wrapper at the Right Boundary

A dangerous mistake is “encrypting” inside `OAuth2AuthorizedClient` and returning an object containing ciphertext to the manager:

```java
// WRONG IDEA: downstream receives ciphertext instead of token.
OAuth2AccessToken token = new OAuth2AccessToken(
    OAuth2AccessToken.TokenType.BEARER,
    "ENCRYPTED_TOKEN_VALUE",
    issuedAt,
    expiresAt);
```

If `loadAuthorizedClient` returns an encrypted token value, `RestClient` may send:

```http
Authorization: Bearer ENCRYPTED_TOKEN_VALUE
```

to the Resource Server. Token values must only be encrypted **on the way down to storage**, and must be decrypted **before constructing the `OAuth2AuthorizedClient` handed to Spring Security**.

### 10.1. Recommended Adapter Architecture

```text
Spring Security OAuth2AuthorizedClientManager
                |
                | loadAuthorizedClient(registration, principal)
                v
Custom SecureOAuth2AuthorizedClientService
                |
                | 1. Lookup encrypted persistence record
                | 2. Verify tenant/principal/registration binding
                | 3. Decrypt access/refresh token values
                | 4. Reconstruct OAuth2AuthorizedClient
                v
Manager receives plaintext token in process memory
                |
                v
HTTP Authorization: Bearer actual-token

saveAuthorizedClient:
  manager -> service -> encrypt token values -> DB

removeAuthorizedClient:
  manager -> service -> delete record + lifecycle handling
```

### 10.2. Persistence Interface Pseudocode

```java
// Design pseudocode, NOT a production implementation.
interface EncryptedAuthorizedClientStore {
    EncryptedRecord find(
        String registrationId,
        String principalKey,
        String tenantId);

    void upsertAtomically(
        EncryptedRecord encryptedRecord,
        long expectedVersion);

    void delete(
        String registrationId,
        String principalKey,
        String tenantId);
}

interface TokenProtector {
    EncryptedPayload encrypt(
        String tokenValue,
        TokenContext authenticatedContext);

    String decrypt(
        EncryptedPayload payload,
        TokenContext authenticatedContext);
}
```

Types `EncryptedRecord`, `EncryptedPayload`, and `TokenContext` are **application-defined types**; they are not Spring Security built-in APIs. Algorithm/encoding/key lifecycle choices require security review.

### 10.3. Java Adapter Skeleton Pattern with Clear Boundaries

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;

final class SecureAuthorizedClientService
        implements OAuth2AuthorizedClientService {

    private final EncryptedAuthorizedClientStore store;
    private final TokenProtector protector;
    private final AuthorizedClientRecordMapper mapper;

    SecureAuthorizedClientService(
            EncryptedAuthorizedClientStore store,
            TokenProtector protector,
            AuthorizedClientRecordMapper mapper) {
        this.store = store;
        this.protector = protector;
        this.mapper = mapper;
    }

    @Override
    @SuppressWarnings("unchecked")
    public <T extends OAuth2AuthorizedClient> T loadAuthorizedClient(
            String registrationId, String principalName) {

        // 1. Resolve trusted tenant/security scope (not raw user input).
        // 2. Find matching encrypted record by trusted composite identity.
        // 3. Verify AAD, key version, record integrity and lifecycle state.
        // 4. Decrypt actual access/refresh tokens in controlled memory.
        // 5. Reconstruct OAuth2AuthorizedClient with plaintext token objects.
        throw new UnsupportedOperationException(
            "Architecture skeleton only");
    }

    @Override
    public void saveAuthorizedClient(
            OAuth2AuthorizedClient authorizedClient,
            Authentication principal) {

        // Encrypt token values, preserve issuedAt/expiresAt/scopes.
        // Bind ciphertext to registration/principal/tenant.
        // Use atomic save/CAS for refresh rotation correctness.
        throw new UnsupportedOperationException(
            "Architecture skeleton only");
    }

    @Override
    public void removeAuthorizedClient(
            String registrationId, String principalName) {

        // Delete local credentials and write deletion/revocation event.
        throw new UnsupportedOperationException(
            "Architecture skeleton only");
    }
}
```

**This is an illustrative skeleton, intentionally non-runnable.** It must not be placed into the application context without implementing the store, mapper, token protector, tenant binding, error handling, concurrency, and tests. In particular, never use placeholder ciphers or roll custom AES-GCM from unreviewed snippets.

### 10.4. Can JdbcOAuth2AuthorizedClientService Be Reused?

`JdbcOAuth2AuthorizedClientService` provides extension points such as a row mapper and parameter mapper. However, if you want column-level encryption:
- You must encrypt on save;
- You must decrypt on load;
- Preserve compatibility with token types/scopes/timestamps;
- Use appropriate AAD and metadata keys;
- Handle migrations;
- Ensure the row mapper does not accidentally produce plaintext logs.

A custom service/persistence adapter can be clearer when adding tenant keys, ciphertext formats, and CAS. Do not replace a JWT decoder bean or RestClient interceptor to perform storage encryption.

---

## 11. Encryption Key Lifecycle and Backup Retention

A backup containing ciphertext without the matching key cannot restore token values.

### 11.1. Key Versions Must Travel with the Data

For example:

```text
DB snapshot 2026-11-01
  token encrypted with key-v2

Live DB 2026-11-16
  token encrypted with key-v4

Disaster restore from Nov 01:
  app must still decrypt key-v2 records,
  or deliberately discard/re-authorize them
```

If `key-v2` has already been destroyed while backups are still expected to restore, RTO may be missed. If policy **intentionally crypto-erases** data by destroying the key, explicitly document that those backups can no longer be used to recover tokens.

### 11.2. Rotation Involves Two Distinct Actions

- **Rotate KEK / rewrap DEK:** replace the key used to protect the DEK; depending on design, may not require re-encrypting every token ciphertext.
- **Rotate DEK / re-encrypt token values:** produce new ciphertext and manage old key versions during migration.

Do not assume changing a key alias in configuration means all records and snapshots have been re-encrypted.

### 11.3. Key Custody

- KMS/HSM with dedicated IAM;
- Never store master keys in source code, database rows, or alongside backups;
- Workload identities get minimal decrypt permissions;
- Backup operators do not necessarily need decrypt permissions;
- Have break-glass workflows with multi-person approval where appropriate;
- All decrypt API calls emit non-sensitive audit metadata;
- Have a restore plan when the primary region's KMS experiences an outage.

### 11.4. Crypto-Erasure and Per-User Deletion

If you want to erase user A's data across **all snapshots** by destroying a key, appropriate key granularity is needed, such as a **per-user/per-tenant DEK**. If all users share a single DEK, destroying that DEK wipes everyone's data.

Crypto-erasure must prove:
- No plaintext DEK copies or unwrappable wrapped-DEKs remain;
- No plaintext token copies exist in logs/dumps/exports;
- KMS backups/key escrow cannot inadvertently restore access;
- Which key serves which data is accurately tracked.

Do not claim “deleted from all backups” merely because a KMS alias or a primary DB row was deleted.

---

## 12. Backing Up a System with Refresh Token Rotation

This is the most critical operational scenario in this lesson.

### 12.1. Refresh Token Rotation Continuously Changes Data

Suppose:

```text
T1:
  Active DB stores R1
  Backup snapshot stores R1

T2:
  Client uses R1 to refresh
  AS returns access token A2 + refresh token R2
  AS invalidates R1
  Active DB stores R2

T3:
  Disaster -> restore backup from T1
  Restored DB now stores R1
  AS expects current R2, R1 already invalid
```

If the restored instance tries to use `R1`:
- The AS may return `invalid_grant`;
- If the AS enforces reuse detection / token-family policies, using old `R1` can be treated as a replay and **cause the entire active token family to be revoked**;
- Other client instances currently using `R2` also lose their sessions;
- The user must initiate a new authorization flow.

Under OAuth 2.0 Security BCP (RFC 9700), refresh-token rotation/reuse detection is an important anti-replay mechanism, especially for public clients.

### 12.2. Why Not Auto-Refresh in Bulk Right After Restore?

A disaster restore can bring back thousands of old refresh tokens. If the app immediately runs batch reauthorization:
- Many `invalid_grant` errors happen concurrently;
- The AS token endpoint suffers heavy load;
- Reuse detection can revoke numerous token families;
- The system generates login errors and support alerts;
- Logs may capture sensitive data if debug logging is excessive.

**Recommendation:** maintain a **quarantine/reconciliation mode** flag for restored authorized-client records, especially user-delegated refresh tokens. Do not fire bulk refresh requests for old records until classified according to policy.

### 12.3. Safe Recovery Strategies

| Option | When appropriate | Notes |
| --- | --- | --- |
| **Discard all restored refresh tokens** | Reauthorization is acceptable | Users log in/consent again |
| Reconcile token-state/generation from authoritative metadata | AS/integration provides a valid mechanism | Do not guess from access token expiry |
| Quarantine by snapshot timestamp, reissue under control | Clear recovery process exists | Avoid triggering bulk reuse detection |
| Proactively revoke via supported AS API | Credential compromise incident | May disrupt users |
| Let machine clients acquire new tokens | `client_credentials` | No need to restore refresh tokens |
| Read-only warm-up before resuming | Want to verify mappings/key config | Do not use stale tokens to call the AS |

**There is no standard universal OAuth2 API for a client to ask “has refresh token R1 been rotated?” without using the token.** Some AS implementations have proprietary admin/revocation/introspection policies. If there is no way to verify, the safe option may be discarding restored tokens and reauthorizing.

### 12.4. Default Spring Manager May Delete Records on invalid_grant

`AuthorizedClientServiceOAuth2AuthorizedClientManager` has default failure handling: when reauthorization fails with `invalid_grant`, the stale authorized client can be removed from `OAuth2AuthorizedClientService`.

This is useful behavior to avoid reusing invalid credentials, **but it is not a complete restore solution**:
- It may already have triggered AS reuse detection before deletion;
- User reauthorization UX must be prepared;
- Infinite request retries must be avoided;
- The same stale record must not be restored again in the next DR event.

### 12.5. Concurrent Refresh Token Rotation in a Cluster

Even **without restoring a backup**, two instances can read the same `R1` before either updates `R2`.

```text
Node A reads R1
Node B reads R1

A refreshes R1 -> gets R2 -> saves R2
B refreshes R1 -> invalid_grant / reuse event

Potential impact:
  AS revokes token family
  User must reauthorize
```

A shared storage backend does not implicitly provide **per-authorized-client refresh locking/CAS**. With a rotation-enabled AS and multiple instances, consider:
- Distributed lock with TTL/fencing;
- Optimistic version checks;
- Single-flight refresh per `(registration, principal, tenant)`;
- Retry/re-read logic that never reuses a stale refresh token;
- Fail closed on conflict;
- Tests covering concurrent refresh.

### 12.6. Do Not Use Backups to “Roll Back Token Versions”

If the DB currently holds `R2` and an operator restores a row with `R1` thinking “the previous token still works,” that violates rotation semantics. Backups exist to restore **still-valid data**, not to negate current authorization state at the AS.

---

## 13. Backups and Data Deletion Are Not Independent

A user may:
- Log out;
- Unlink a provider;
- Revoke consent at the OP;
- Request deletion of linked data;
- Be locked out or lose tenant access;
- Be offboarded from the organization.

### 13.1. Delete Live Data First, Then Handle Copies

```text
User unlinks Company SSO
      |
      v
1. Verify authenticated user + ownership
2. Mark credential disconnected / revoked in authoritative ledger
3. Stop new token usage
4. Revoke at AS if supported/policy requires
5. Remove authorized client from active store
6. Invalidate in-memory caches/replicas
7. Record deletion event without token value
8. Let backup retention/crypto-erasure policy handle snapshots
```

**RP logout does not necessarily delete every authorized client.** One application may want to keep tokens so users do not have to re-consent; another product requires immediate deletion upon logout. Distinguish **browser session logout**, **disconnect account**, **revoke grant**, and **delete stored credentials** per the business contract.

### 13.2. Deletion in Backups Can Lag Behind Live Deletion

Many backup systems keep immutable snapshots for a fixed retention window. You cannot surgically delete a single row from all immutable snapshots without rebuilding the entire artifact.

Risk-reduction mechanisms:
- Shortest backup retention meeting RPO/RTO/compliance;
- Isolated encrypted storage;
- Per-user/tenant crypto-erasure if supported by the design;
- Durable delete/revoke ledger;
- Restore procedures replaying tombstones **before enabling token usage**.

### 13.3. Do Not Resurrect Deleted Rows on Restore

```text
Day 1: snapshot contains authorized_client(U1)
Day 5: user U1 unlinks account -> live DB deletes U1
Day 8: disaster -> restore Day 1 snapshot
       |
       v
Without tombstones:
  U1 token record reappears (BAD)

With deletion ledger newer than snapshot:
  Replay unlink event before app resumes
  Remove U1 record
  Do not use its refresh token
```

**This is a correctness requirement independent of token encryption.** A backup can be strongly encrypted and still violate data-deletion expectations if a restore brings revoked records back to life.

### 13.4. Designing a Tombstone Ledger

Needed metadata may include:
- Stable internal principal identifier;
- Registration ID/issuer;
- Tenant identifier;
- Deletion/revocation event version and timestamp;
- Causal request/audit ID;
- Legal/retention policy class.

Must not contain raw access tokens or refresh tokens.

Example event:

```json
{
  "event_type": "authorized_client_disconnected",
  "tenant_id": "tenant-a",
  "principal_key": "principal-key-123",
  "registration_id": "company-login",
  "event_version": 42,
  "occurred_at": "2026-11-16T09:00:00Z"
}
```

This is an **application-defined data model**, not a Spring Security built-in event schema.

### 13.5. User Deletion Permissions vs. Admin/Service Permissions

Do not expose:

```http
DELETE /api/authorized-clients?principal=someone-else
```

and directly call `removeAuthorizedClient` from raw input. Always verify **the caller is authorized to remove that link**, tenant boundaries, registration ID allowlists, and auditing—never allowing one user to delete or tamper with another user's credentials.

---

## 14. Removing Local Authorized Clients via the Service

Example service-level operation:

```java
package example.security;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.stereotype.Service;

@Service
public class AuthorizedClientLifecycleService {

    private final OAuth2AuthorizedClientService clients;

    public AuthorizedClientLifecycleService(
            OAuth2AuthorizedClientService clients) {
        this.clients = clients;
    }

    public void disconnectVerifiedPrincipal(
            String registrationId,
            String trustedPrincipalKey) {

        // Caller must prove ownership + tenant authorization
        // BEFORE entering this method.
        clients.removeAuthorizedClient(
            registrationId, trustedPrincipalKey);
    }
}
```

**This only deletes the local cache/store entry.** If business logic requires revoking tokens at the AS, the workflow must know:
- Which token(s) to revoke;
- Which trusted AS endpoint/credentials to use;
- Whether to revoke the refresh token or access token;
- If the AS is unreachable, whether local deletion executes first;
- Whether durable retry/outbox is needed;
- Timeout/error semantics and user-facing state.

### 14.1. Token Revocation Under RFC 7009

RFC 7009 defines the token revocation endpoint for OAuth2. However:
- Not every AS exposes or supports the same endpoint;
- Confidential clients typically require authentication;
- The request body contains a **sensitive token value**;
- Success of local deletion does not prove remote revocation;
- Per the spec, the revocation response may not reveal whether the token existed.

If remote revocation at the AS is not possible, at a minimum prevent local token reuse and log an incident/follow-up per security policy. Never send tokens to a revocation URI taken from untrusted input.

---

## 15. Tenant, Issuer, and Principal Isolation

Default JDBC schema primary key:

```text
(client_registration_id, principal_name)
```

This **does not include an independent tenant ID in the primary key**.

In a multi-tenant system, verify with certainty:
- Whether the same `principal_name` can collide between Tenant A and Tenant B;
- Whether the same `sub` from two issuers can collide;
- Whether user identities map to a unique internal principal ID;
- Whether registration IDs are tenant-specific or shared;
- Who is authorized to call `loadAuthorizedClient` for that key.

### 15.1. Do Not Use Email as a Global Key

```text
issuer Company: sub=42, email=alice@example.test
issuer Partner: sub=42, email=alice@example.test
```

This does not prove the two accounts belong to the same person. For OIDC, the minimum identity key is **(issuer, subject)**. If an internal principal ID is used, it must be created by an explicit account-linking policy and never reused across tenants.

### 15.2. Composite Identity in a Custom Store

An illustrative design:

```text
tenant_id
issuer_id
client_registration_id
principal_key
token_kind
record_version
```

Use these fields to:
- Query exact records;
- Enforce authorization/tenant boundaries;
- Bind AAD during encryption;
- Lock/CAS refresh token rotation;
- Delete according to user/tenant policy.

Do not alter the primary key of Spring's `oauth2_authorized_client` table and expect `JdbcOAuth2AuthorizedClientService` to understand the new composite key. A fully designed custom DAO/service or custom mapping is required.

### 15.3. Service Principal for client_credentials

For `client_credentials`, use a stable name such as:

```text
registrationId = reports-machine
principalName  = reports-batch
```

so the cache can reuse tokens. However, if the same app serves multiple tenants with different permissions, a single shared principal can lead to **cross-tenant token reuse**. Cache keys must reflect tenant/resource scope and the AS-issued audience as appropriate.

---

## 16. Operational Retention Job: How to Delete Records Safely?

### 16.1. Why Not DELETE All Expired Access Tokens?

Wrong:

```sql
DELETE FROM oauth2_authorized_client
WHERE access_token_expires_at < CURRENT_TIMESTAMP;
```

If a row has a valid refresh token, this query wipes out the ability to renew it. The result can be mass forced re-logins.

### 16.2. More Restrictive Cleanup Candidates

With the stock table on PostgreSQL, here is a query **only to inspect candidates**:

```sql
SELECT
    client_registration_id,
    principal_name,
    access_token_expires_at,
    created_at
FROM oauth2_authorized_client
WHERE refresh_token_value IS NULL
  AND access_token_expires_at < CURRENT_TIMESTAMP - INTERVAL '7 days';
```

This query intentionally performs only a **SELECT**. A production retention job must also determine:
- Whether the record is in use by a running job;
- Whether metadata retention is required;
- Whether a recent authorization/update race is occurring;
- Applicable tenant/deletion policies;
- Whether records are permitted to be deleted after that duration.

**The 7-day figure is purely an illustrative buffer for learning, not a default policy.**

### 16.3. When Deleting, Use an Atomic, Bounded Strategy

Example transaction-level pseudocode:

```text
1. Acquire appropriate lifecycle lock / version predicate
2. Select candidates by approved policy
3. Recheck current record version and grant status
4. Delete by exact trusted key
5. Write non-sensitive deletion event / audit
6. Commit
7. Emit aggregate metric (count), no token values
```

Do not run a bulk delete of 10 million rows in a single transaction where DB locking is a risk. Use batching/monitoring and respect replica lag, PITR, and backup load.

### 16.4. Do Not Retain Stale Access Tokens for “Audit” Purposes

If auditing is needed, store:
- Registration ID;
- Pseudonymous principal key;
- Issuer category;
- Token issuance/expiry timestamps;
- Scope category;
- Outcome;
- A **non-reusable** token fingerprint if genuinely required and reviewed.

Do not keep raw tokens just to answer “which token did the user use.” Token values are credentials, not log fields.

### 16.5. Retention Policies Must Be Enforced Across All Layers

A row deleted from the primary database can still exist in:
- Lagging replicas;
- WAL/binlog;
- Backup vaults;
- Storage snapshots;
- Test exports;
- Application caches;
- Heap dumps;
- Audit logs.

The policy must describe expected lag and deletion/crypto-erasure per system, not just a single SQL `DELETE`.

---

## 17. Standard Backup/Restore Runbook

### 17.1. Pre-Incident: Preparation

1. Decide whether authorized-client tokens are backed up at all.
2. Classify registrations: machine vs. delegated, AS/protocol properties, refresh rotation.
3. Document the source of truth for revocation, disconnect, and deletion events.
4. Design database backup, retention, encryption, and IAM.
5. Verify key versions and ability to unwrap historical ciphertext.
6. Document the backup manifest: timestamp, DB schema version, key versions, checksum.
7. Run restore tests in an isolated environment that never uses production tokens to call the AS.
8. Have a kill switch to pause outbound token refreshes or bulk jobs.
9. Have a reauthorization/AS rate-limiting plan.
10. Define RPO/RTO and measurable success criteria.

### 17.2. During Incident: Controlled Recovery

```text
Incident declared
      |
      v
Freeze token mutation / active refresh where possible
      |
      v
Restore DB snapshot into isolated target
      |
      v
Verify backup integrity + schema + key version
      |
      v
Replay deletion/revocation ledger after snapshot
      |
      v
Quarantine potentially stale rotated refresh tokens
      |
      v
Purge/reconcile tokens by approved policy
      |
      v
Smoke test with synthetic machine client / test AS
      |
      v
Resume low-risk traffic gradually
      |
      v
Monitor invalid_grant, 401, 403, refresh activity
      |
      v
Post-incident audit + update runbook
```

### 17.3. Do Not Restore Directly Into a Live Environment

If the app is currently using `R2` while a restore writes `R1`, concurrent refreshes can trigger reuse detection. Therefore, best practice is to:
- Isolate the restored database;
- Stop/freeze relevant mutation workloads;
- Reconcile token state and deletion events;
- Re-open traffic gradually;
- Have a rollback/forward recovery plan.

### 17.4. If You Cannot Be Sure a Token Is Still Valid

**Discarding the local token and reauthorizing** is usually safer than attempting to use old refresh tokens in bulk. Especially when the AS enforces strict token rotation, “testing” real tokens can alter token-family state.

### 17.5. If a Backup or Key Shows Signs of Compromise

This is a **security incident**, not merely an availability issue:
- Block further backup access;
- Collect access logs/forensics per procedure;
- Identify affected tokens/registrations/tenants;
- Consider revoking tokens and rotating client credentials/keys;
- Reduce privileges of compromised identities;
- Assess the scope of exposed personal data/credentials;
- Notify according to policy and applicable obligations;
- Never restore a snapshot suspected of tampering without verifying integrity.

---

## 18. Recovering Without Sending Users Into Infinite Login Loops

A sensible recovery UX:

```text
Restored app receives user request
      |
      v
Load authorized client
      |
      +-- record quarantined/revoked?
      |      -> do not use token
      |      -> redirect to safe reauthorization flow
      |
      +-- access token still valid?
      |      -> may continue if trusted and allowed
      |
      +-- refresh token state uncertain?
             -> controlled reauth instead of blindly retrying
```

**Do not write**:

```java
while (true) {
    try {
        refreshTokenAgain();
    } catch (Exception ignored) {
        // Retry forever.
    }
}
```

An infinite loop can hit AS rate limits, spike `invalid_grant` errors, and mask the root cause of restoring stale tokens.

### 18.1. Difference Between Reauthorization and Login

- Redirecting the user to the authorization endpoint may be needed to obtain a new grant.
- The OP SSO session may still be active, so no password entry is needed, yet a **new authorization transaction** still occurs.
- `client_credentials` can acquire new tokens without user involvement.
- Never take an old ID Token or refresh token to forge a new `Authentication` while bypassing state/PKCE/nonce/issuer validation.

### 18.2. Browser Logout Does Not Automatically Revoke All Tokens

A user logging out of the RP session may not require revoking authorized-client grants. Only if the product specifies “Disconnect Google account” should that action delete/revoke tokens per policy.

Documentation should clearly distinguish these behaviors, especially since users often assume “sign out” means “no tokens remain stored.”

---

## 19. Handling invalid_grant and Failure Handlers

An `invalid_grant` on refresh usually means the token is no longer usable, which can be caused by:
- Token expired/revoked;
- Refresh token already rotated;
- Client credentials/registration changed;
- Grant no longer eligible;
- AS policy changed.

### 19.1. Service Manager

For scheduled/service-tier code:

```java
@Bean
OAuth2AuthorizedClientManager backgroundManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientService clients) {

    OAuth2AuthorizedClientProvider provider =
        OAuth2AuthorizedClientProviderBuilder.builder()
            .refreshToken()
            .clientCredentials()
            .build();

    AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
        new AuthorizedClientServiceOAuth2AuthorizedClientManager(
            registrations, clients);

    manager.setAuthorizedClientProvider(provider);
    return manager;
}
```

Imports used:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
```

**Warning:** A provider builder like the one above must match each registration's grant configuration. It cannot run an authorization-code browser flow or nonce validation inside a scheduled thread.

### 19.2. Default invalid_grant Removal

Spring Security's manager includes default failure handling to remove stale authorized clients as appropriate upon `invalid_grant`.

If the application overrides `setAuthorizationFailureHandler(...)`, ensure it:
- Does not keep stale tokens indefinitely;
- Does not mistakenly delete a token just updated by another instance;
- Can audit a non-sensitive failure category;
- Has a reauthorization policy;
- Never turns one user's error into deleting another user's token.

### 19.3. Downstream 401 Differs from Refresh invalid_grant

A Resource Server returning HTTP 401 `invalid_token` does not automatically mean the refresh token is invalid; it may stem from audience/issuer mismatch, expiration, or revocation.

When using `OAuth2ClientHttpRequestInterceptor`, a failure handler can be configured to remove invalid authorized clients per contract. Do not blindly retry every 401 indefinitely; inspect the AS/RS error and token state first.

### 19.4. Backup Restore Must Not Reinstate Stale Tokens Removed by Handlers

If login/refresh fails due to stale `R1` and the manager deletes the record, a replication/restore job must not overwrite it back with `R1` from an old snapshot. The deletion/version ledger must take precedence over older backup data.

---

## 20. Backup with Reactive Components

In WebFlux, the corresponding abstractions are:

- `ReactiveOAuth2AuthorizedClientService`;
- `ServerOAuth2AuthorizedClientRepository`;
- `InMemoryReactiveOAuth2AuthorizedClientService`;
- `ReactiveOAuth2AuthorizedClientManager`;
- `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`.

### 20.1. Reactive Services Do Not Use Servlet Services

```text
Servlet:
  OAuth2AuthorizedClientService
  loadAuthorizedClient(...) -> OAuth2AuthorizedClient

Reactive:
  ReactiveOAuth2AuthorizedClientService
  loadAuthorizedClient(...) -> Mono<OAuth2AuthorizedClient>
```

A `JdbcOAuth2AuthorizedClientService` using blocking JDBC should not be invoked directly on the Netty event loop during Reactive request processing.

If persistent authorized clients are needed in WebFlux:
- Choose an appropriate reactive persistence/DAO or a blocking adapter offloaded in a controlled manner;
- Preserve cache-key, encryption, refresh rotation, and deletion semantics;
- Compose publishers properly;
- Never call `.block()` inside a request handler.

### 20.2. Encryption in a Reactive Pipeline

```text
ReactiveOAuth2AuthorizedClientService.load(...)
    -> load encrypted record asynchronously
    -> decrypt under authorized workload key policy
    -> build OAuth2AuthorizedClient
    -> Mono<OAuth2AuthorizedClient>
```

KMS calls may involve network I/O or a blocking SDK. If the SDK is blocking, configure the proper scheduler along with timeout/backpressure/circuit-breaker policies; never run long blocking operations on the Reactor event loop.

### 20.3. Reactive Cache and Refresh Concurrency

Two concurrent subscriptions can trigger authorize/refresh simultaneously. If persistence uses optimistic locking:
- Query/update by record version;
- On CAS conflict, re-read the current token;
- Never reuse an already-rotated refresh token;
- Never leak tokens across tenants or publishers;
- Test with `StepVerifier` and concurrent subscriptions.

**Reactive does not make the rotation problem disappear**; it only changes the API and execution lifecycle.

---

## 21. Logging, Metrics, and Auditing

### 21.1. Minimal Safe Logging

Example event schema:

```json
{
  "event": "authorized_client_storage",
  "action": "load",
  "result": "not_found",
  "registration_id": "company-login",
  "principal_category": "end_user",
  "tenant_category": "enterprise",
  "storage_backend": "jdbc",
  "trace_id": "internal-safe-id"
}
```

This event **contains no tokens**, raw principals/emails, or Authorization headers. It is an application-defined schema, not Spring Security's default log output.

### 21.2. Bounded-Cardinality Metrics

```text
authorized_client_store_operations_total{operation="load",result="success"}
authorized_client_store_operations_total{operation="save",result="failure"}
authorized_client_store_operations_total{operation="delete",reason="disconnect"}
authorized_client_refresh_total{registration="company",result="invalid_grant"}
authorized_client_backup_restore_total{result="success"}
authorized_client_restore_quarantine_total{reason="stale_refresh"}
authorized_client_decrypt_failures_total{key_version="v4"}
```

Never put `tokenValue`, email, `sub`, session IDs, or raw exception messages into metric labels.

### 21.3. Auditing Who Reads Credentials

Permission to read a DB row should not automatically grant visibility into raw tokens. Use:
- Database SQL access auditing;
- KMS decrypt auditing;
- Service-level authorization auditing;
- Break-glass approval logs;
- Bulk export alerts;
- No token values inside audit events.

In particular, `loadAuthorizedClient` monitoring can be high-frequency; apply appropriate sampling/aggregation to avoid creating a PII-rich log stream.

### 21.4. Do Not Print the AuthorizedClient Object

Avoid:

```java
log.info("authorizedClient={}", authorizedClient);
log.debug("accessToken={}", client.getAccessToken().getTokenValue());
log.error("refreshToken={}", client.getRefreshToken().getTokenValue());
```

Even if an object's current `toString()` masks tokens, **do not rely on that as a security control**. Maintain the rule of never passing credential-bearing objects to loggers.

---

## 22. Authorized Client Data in Sessions and Cookies

An application may use `HttpSessionOAuth2AuthorizedClientRepository` or an HttpSession-backed repository in certain cases.

This means token data can enter:
- Servlet container memory;
- Redis if Spring Session stores HttpSession;
- Session persistence/swap;
- Session backups/Redis snapshots;
- Browser session identifiers (not necessarily token values).

### 22.1. Browser Cookies Should Not Contain Raw OAuth2AuthorizedClient

Standard session cookies typically hold an **opaque session ID**, not the entire authorized client object. Never serialize token values into unencrypted or unauthenticated cookies.

### 22.2. Redis Persistence Can Back Up Tokens

If Spring Session stores authorized-client objects in Redis:
- Redis AOF/RDB snapshots can contain token data;
- Redis replicas and backups also need encryption and access control;
- Session TTL does not guarantee token bytes vanish immediately from snapshots/WAL;
- Redis key expiration differs from backup artifact retention.

### 22.3. Logout and Invalidation

Invalidating a session deletes tokens **only if tokens are actually stored in that session**. If authenticated principal records are delegated to a JDBC `OAuth2AuthorizedClientService`, session logout does not automatically delete authorized clients in the DB.

**Do not equate session deletion with consent revocation.** Inspect the exact repository/service wiring.

---

## 23. Principal-Scoped Backups and Personal Data

A user may connect multiple providers:

```text
user internal-42:
  company-login -> company access/refresh token
  calendar      -> calendar access/refresh token
  reports       -> reports access token
```

When the user requests “disconnect Calendar,” do not accidentally delete Company login or other users' authorized clients.

### 23.1. Defining Deletion Scope

You may need to target:
- Only a single `registrationId`;
- A `principalKey`;
- A tenant/issuer boundary;
- A specific grant/resource;
- All tokens for a user upon account deletion.

### 23.2. Auditing Without Retaining Credentials

Example audit record:

```json
{
  "subject_key": "internal-42",
  "registration_id": "calendar",
  "action": "disconnect",
  "outcome": "local_deleted",
  "revocation_outcome": "remote_pending"
}
```

Never record access/refresh tokens as evidence.

### 23.3. Data Deletion Must Account for Backups

If backups expire after a policy window, you can:
- Delete active records immediately;
- Block restoration via tombstones;
- Restrict backup access;
- Keep snapshots for the minimum approved duration;
- Consider crypto-erasure where required and supported by the architecture.

This area requires legal/privacy assessment by region and organization; this lesson does not prescribe a universal legal period.

---

## 24. Database Permissions and Anti-Exfiltration Controls

### 24.1. Least-Privilege DB Role

The application only needs appropriate privileges on the authorized clients table, such as:
- `SELECT` to load;
- `INSERT`/`UPDATE` to save;
- `DELETE` to remove;
- Never runtime `DROP TABLE` or `ALTER TABLE`.

Migration tools should use a separate role with schema privileges, not shared with the runtime application.

### 24.2. Separate Backup Account from App Account

Backup jobs have permission to create snapshots per policy, without needing:
- Application KMS token decrypt permissions;
- Permissions to modify production token rows;
- Permissions to delete immutable backups;
- Permissions to read all PII in plaintext.

### 24.3. Network and Transport

- Expose database endpoints only to necessary workloads;
- TLS between app and DB/Redis;
- TLS to AS/RS;
- Never send DB dumps over unencrypted email/chat;
- Enforce egress allowlists for the AS token endpoint and downstream APIs;
- Do not grant full-table debug `SELECT` permissions to routine support roles.

### 24.4. Backups and Encryption Keys Should Not Share a Single Privilege

If a single IAM role can both download all backups and decrypt every token key, compromising one principal is enough to break confidentiality completely. Separating roles, approvals, and auditing reduces the blast radius.

---

## 25. Recoverability After Client Secret or Issuer Changes

Beyond refresh rotation, AS configuration can also change:

```text
Snapshot T1:
  registrationId = company-login
  clientId = portal-client-old
  refresh token R1

Live T2:
  clientId = portal-client-new
  issuer metadata / client auth policy updated
```

After restoring `T1`:
- Current `ClientRegistration` may no longer match old tokens;
- Refresh token `R1` may be bound by the AS to the old client;
- The token endpoint may return `invalid_client` or `invalid_grant`;
- JWKS/issuer/audience policies may have changed;
- Users must reauthorize under the new configuration.

### 25.1. Secret Rotation Does Not Automatically Invalidate Old Tokens

Changing a client secret:
- May keep the client ID and grants intact if the AS supports it;
- May also revoke old tokens depending on policy;
- Does not guarantee all old refresh tokens remain usable.

### 25.2. Do Not Duplicate Client Secrets in the Authorized-Client Table

`ClientRegistration` holds the configured client secret, whereas the standard authorized-client persistence schema stores token metadata and token values—**there is no need to store the client secret in every row**. Keep secret management separate from the token cache to avoid backing up extra copies of client secrets.

### 25.3. Migrating Between Issuers

Never copy tokens from issuer A into issuer B's registration merely because both providers share an email or `sub`. Tokens carry issuer/audience/client bindings; protocol-compliant migration and reauthorization are required.

---

## 26. Engineering Tests for Storage and Backups

A system needs multi-layer tests rather than just seeing “SQL INSERT succeeded.”

### 26.1. Unit Testing the Storage Contract

Test `OAuth2AuthorizedClientService` with synthetic tokens:
- Save then load by exact registration/principal;
- Cannot load under a different principal;
- Remove deletes only the targeted record;
- Does not accidentally delete another registration;
- Access/refresh token values, timestamps, and scopes round-trip accurately;
- No token values are logged.

### 26.2. Creating a Synthetic OAuth2AuthorizedClient

```java
import java.time.Instant;
import java.util.Set;

import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.OAuth2AccessToken;

ClientRegistration registration =
    ClientRegistration.withRegistrationId("reports-machine")
        .clientId("test-client")
        .clientSecret("test-only-secret")
        .authorizationGrantType(
            AuthorizationGrantType.CLIENT_CREDENTIALS)
        .tokenUri("https://auth.example.test/token")
        .scope("reports.read")
        .build();

Instant now = Instant.now();

OAuth2AccessToken token =
    new OAuth2AccessToken(
        OAuth2AccessToken.TokenType.BEARER,
        "synthetic-access-token",
        now,
        now.plusSeconds(600),
        Set.of("reports.read"));

OAuth2AuthorizedClient client =
    new OAuth2AuthorizedClient(
        registration, "reports-batch", token);

var principal =
    new TestingAuthenticationToken(
        "reports-batch", "not-a-real-password");

service.saveAuthorizedClient(client, principal);

OAuth2AuthorizedClient loaded =
    service.loadAuthorizedClient(
        "reports-machine", "reports-batch");
```

`service` in this snippet is an `OAuth2AuthorizedClientService` configured in the test context, such as `JdbcOAuth2AuthorizedClientService` or a custom encrypted service.

**Never use this fixture token to call real APIs.** It is a synthetic value solely for verifying the persistence contract.

### 26.3. JDBC Integration Tests

Against a migrated test database container:
- Insert/save a synthetic authorized client;
- Close the application context/test transaction;
- Initialize another service instance against the same database;
- Reload the record;
- Verify decryption/deserialization succeeds;
- Test cleanup/removal;
- Test failure handling when the registration has been removed from `ClientRegistrationRepository`;
- Test schema migration versions.

**If the goal is testing encryption**, assert that raw database token bytes **do not contain** `synthetic-access-token` and ciphertext differs from plaintext; also verify auth tag/AAD tampering is rejected. Do not dump binary data into test logs.

### 26.4. Backup Restore Rehearsal

A test drill must verify:
1. The database snapshot artifact exists and has a checksum;
2. KMS/key versions are still sufficient to decrypt;
3. Restore happens in an isolated namespace/cluster;
4. Application/schema migrations are compatible;
5. Synthetic token records round-trip properly;
6. Restore does not reactivate deleted principals;
7. Stale refresh tokens are quarantined/discarded per policy;
8. Logs contain no tokens/secrets;
9. Backup access is audited;
10. RPO/RTO are measured.

### 26.5. Tampering Tests

- Modify ciphertext bytes -> decryption/authentication tag failure;
- Copy ciphertext to another registration -> AAD mismatch;
- Copy Tenant A's token to Tenant B -> rejected;
- Use an invalid/retired key version -> explicit failure/recovery;
- Replay an old encrypted record version -> blocked by storage/version policy if supported by the design.

Never fall back to “if decryption fails, treat ciphertext as plaintext.” That is a dangerous credential-exposure and logic bypass flaw.

---

## 27. Testing Refresh Token Rotation and Stale Restores

A stateful mock provider:

```text
AS token-state:
  current_refresh_token = R1
  R1 valid

Client DB:
  R1

Backup:
  R1

First refresh:
  R1 -> access A2 + refresh R2
  AS marks R1 used
  DB saves R2

Restore old backup:
  DB now R1

Attempt refresh R1:
  AS -> invalid_grant
  possible token-family reuse action
```

### 27.1. Critical Assertions

| Scenario | Expected |
| --- | --- |
| First refresh with R1 | R2 stored after success |
| Second refresh with R1 | AS rejects |
| Restoring R1 when AS already issued R2 | Does not send R1 in bulk automatically |
| Invalid_grant | Local stale record removed/quarantined, no infinite retry |
| Two replicas refresh concurrently | No cross-user/token mix-up; clear CAS/locking behavior |
| User disconnected before snapshot restore | Tombstone removes the record |
| AS outage during restore | Do not treat outage as consent revoked without evidence |
| Client_credentials token expired | Acquire new token using client credentials |

### 27.2. Use a Mock AS, Never Production Tokens

Never test replay with a real user's refresh token. Attempting to use an already-rotated token can cause the AS to revoke the active token family.

### 27.3. Do Not Conflate invalid_grant with Downstream HTTP 401

`invalid_grant` typically comes from the **token endpoint** regarding the grant/code/refresh token. HTTP 401 `invalid_token` typically comes from a **Resource Server**. Both have different failure handlers and remediations.

---

## 28. A Testable Deletion Workflow

Suppose a user chooses **Disconnect Calendar**.

```text
POST /settings/integrations/calendar/disconnect
  |
  v
Authenticated user + tenant policy
  |
  v
Resolve trusted principal key + calendar registration
  |
  v
Mark disconnected in durable ledger
  |
  v
Cancel new API jobs for calendar
  |
  v
Attempt remote token revocation if supported
  |
  v
Delete local authorized-client record
  |
  v
Invalidate caches / replicas
  |
  v
Acknowledge local disconnect state
```

### 28.1. Test Cases

- User A can only delete A's token;
- User A cannot delete B's token;
- Tenant A cannot delete Tenant B's token;
- Deleting Calendar does not delete Company login;
- AS revocation 503 is durably recorded as pending if policy requires retry;
- Local tokens cannot be used after disconnect;
- Backup restore does not resurrect disconnected records;
- Audit events contain no raw tokens;
- API is idempotent if the user clicks Disconnect twice.

### 28.2. Idempotent Deletion

Calling `removeAuthorizedClient(registrationId, principalName)` a second time when the record is already gone should be treated as idempotent in the domain layer if required. However, do not conclude that the AS revocation call succeeded merely because local deletion returned without error.

### 28.3. Token Status and Privacy Status Differ

A token may still be valid at the AS while the user has disconnected on the RP. **A domain disconnected flag must block local use immediately**, rather than relying on whether the AS token has expired.

---

## 29. Runbook for Protecting Data Exports and Test Environments

### 29.1. Prohibit Direct Production DB Clones Containing Tokens

An anti-pattern:

```text
pg_dump production
  -> import into dev database
  -> all refresh tokens copied to low-security environment
```

Alternatives:
- Synthetic token data;
- Sanitization scripts running **inside the production security boundary** prior to export;
- Drop or replace token columns;
- Strip client secrets and unnecessary PII;
- Use test principals/registrations;
- Verify no secondary WAL/snapshot containing plaintext credentials enters the export package.

### 29.2. Sanitize Data While Preserving Schema

A test dataset may need:
- Record counts;
- Anonymized scope distributions;
- Synthetic token `issuedAt`/`expiresAt`;
- Synthetic registration IDs;
- Synthetic principal keys;
- Expired/revoked/corrupt states.

Real access/refresh tokens are unnecessary for testing retention or indexing.

### 29.3. Never Let Test Environments Call Production AS/RS

Even when tokens are sanitized, `ClientRegistration` may still point to production token URIs. Ensure:
- Test registration endpoints are allowlisted;
- Network egress restrictions are enforced;
- Test-only secrets are used;
- Explicit profiles are active;
- Tests fail if a token URI targets a production host.

---

## 30. Operational Monitoring and Alerting

Metric groups:

| Metric | Meaning | Response |
| --- | --- | --- |
| Authorized client load miss rate | Token not found in cache | Check expected reauth vs. storage outage |
| DB read/write errors | Persistence unavailable | Bounded retry/backoff, incident |
| KMS decrypt failures | Key/format/tampering issue | High-severity alert, fail closed |
| Refresh invalid_grant spike | Stale tokens, rotation race, AS policy | Quarantine, investigate refresh concurrency |
| User reauthorization rate | UX impact after restore/retention | Capacity/UX review |
| Backup job failures | RPO at risk of breach | Restore readiness alert |
| Backup restore drill failures | RTO uncertain | Do not declare DR-ready until passing |
| Backup vault access anomalies | Possible credential exfiltration | Security incident |
| Growth of expired rows | Cleanup/retention job failing | Inspect deletion policy and jobs |
| Deletion ledger replay lag | Restore risks resurrecting records | Block resume until caught up |
| Sudden spike in token issuance rate | Cache misses / cluster refresh race | Analyze manager principals/cache |

### 30.1. Never Put Raw Tokens Into Metrics

Wrong:

```text
authorized_client_cache_entries{token="eyJhbGci..."} 1
```

Right:

```text
authorized_client_cache_entries{registration="company",state="active"} 1234
```

Only use allowlisted labels containing no PII/secrets.

### 30.2. Distinguish Backup Success from Restore Success

```text
backup_created_total{result="success"} 1
restore_drill_total{result="failure_key_unavailable"} 1
```

A successful snapshot that cannot be decrypted does not meet DR goals. Schedule regular **restore rehearsals**, rather than only monitoring backup job exit codes.

---

## 31. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| “The access token expired, so backing up tokens is harmless” | Snapshots may still hold refresh tokens or identifying data |
| “BLOB in JDBC means encrypted” | BLOB/BYTEA is a binary storage type, not encryption |
| “TDE is enabled, so DBAs cannot SELECT tokens” | TDE does not stop authorized SQL readers |
| “Encrypted backups are enough” | Key custody, restore integrity, IAM, and token rotation still matter |
| “Restoring R1 will work just like on backup day” | The AS may already have rotated/revoked R1 |
| “On invalid_grant, just keep retrying” | Can trigger reuse detection and worsen outages |
| “ClientCredentials also needs refresh token backups” | This grant usually issues no refresh token; tokens can be re-acquired |
| “Logout always deletes OAuth2AuthorizedClient” | Depends on repository/service wiring and business policy |
| “removeAuthorizedClient automatically revokes at the AS” | It only deletes the local record |
| “Deleting a DB row removes it from all backups” | WAL/snapshots/exports remain within the retention window |
| “Any user can share email as principalName key” | Issuer/tenant/account-linking isolation is required |
| “A shared database prevents refresh races” | Atomicity/locking/CAS is required if the AS enforces rotation |
| “Having the right scope makes a token valid for any API” | Audience/issuer/signature/expiry must also be validated |
| “Application encryption replaces IAM” | App compromise can capture both tokens and keys; defense in depth is needed |
| “Hash tokens and store the hash instead of token value” | One-way hashes cannot be used to call APIs or refresh |
| “If decrypt fails, fall back to reading plaintext” | Fail-open behavior that can leak or abuse credentials |
| “Testing SQL insert means DR is tested” | Restore, key, deletion, and rotation drills are required |
| “Keep backups as long as possible” | Longer retention increases attack surface and data-handling obligations |
| “Nobody can read cloud snapshots” | Encryption, access grants, copies, and auditing must be verified |
| “We can test restore using a production refresh token” | Risks revoking active token families and exposing real data |

---

## 32. Case Studies

### Case 1 — Service Using Only client_credentials

A scheduled worker calls the Reports API and can request fresh tokens from the AS.

**Should the token cache be backed up?**

> You can choose **not to back up the access-token cache** if reauthorization and AS capacity are acceptable. Business backups still need separate protection.

### Case 2 — User-Delegated Refresh Tokens

A web portal needs users to keep their Calendar connection across multiple weeks.

**What should be protected?**

> Refresh token encryption at rest, IAM/backup encryption, retention policy, revocation/unlink workflow, key lifecycle, and rotation-safe restore handling.

### Case 3 — Database Volume Encryption Enabled

A DBA still has `SELECT refresh_token_value` permissions and sees readable token bytes.

**Expected or unexpected?**

> Expected under TDE's threat model: disk encryption does not prevent authorized database readers. Least privilege and application-level token encryption are needed if protecting against SQL readers is required.

### Case 4 — Restoring an Already-Rotated Token R1

The AS already issued `R2`; the DB is restored from a snapshot containing `R1`.

**Should R1 be refreshed immediately?**

> Not in bulk. It can cause `invalid_grant`/reuse detection. Quarantine/reconcile or discard tokens and reauthorize.

### Case 5 — Access Token Expired, Refresh Token Still Valid

Cleanup SQL deletes every row with `access_token_expires_at < now()`.

**What is the problem?**

> It deletes still-valid refresh tokens, causing unnecessary re-logins. Retention must consider the authorized-client/grant lifecycle, not just the access token.

### Case 6 — User Disconnected, Old Backup Still Holds Token

After restore, a user sees a previously removed connection reappear.

**Root cause?**

> The restore failed to replay deletion/revocation events. Tombstones/ledgers and blocking token use before restore cleanup are required.

### Case 7 — KMS key-v2 Deleted

Last month's backup used `key-v2`; the application now only has `key-v4`.

**Outcome?**

> Older backups may fail to decrypt. Key retention or deliberate token discard/reauthorization is needed; the DR plan must document this clearly.

### Case 8 — Copying Token Ciphertext to Another Tenant

An actor copies Tenant A's ciphertext into Tenant B's row.

**What detects this?**

> AEAD integrity + AAD binding tenant/registration/principal. Storage authorization must also prevent cross-tenant reads/writes.

### Case 9 — Two Nodes Concurrently Refresh R1

Node A saves `R2`; Node B reuses `R1` and gets `invalid_grant`.

**Lesson learned?**

> A shared DB is not enough; per-key concurrency control/optimistic locking and retry logic that never reuses stale refresh tokens are required.

### Case 10 — Deleting OAuth2AuthorizedClient and Assuming Grant Revocation

**Where is the flaw?**

> `removeAuthorizedClient` deletes only the local copy; the AS may still honor the token. Integrate the revocation endpoint when required by policy and supported.

### Case 11 — Lost Access Token Backup, No Business Record Loss

The application supports only `client_credentials`.

**Recovery strategy?**

> Re-acquire machine tokens once the AS is available; no need to restore historical tokens if the token cache is disposable.

### Case 12 — Token Contains PII in the JWT Payload

An admin says “the JWT is signed, so its contents cannot be read.”

**Assessment?**

> False. Signatures protect integrity, not claim confidentiality. A JWT can be decoded unless encryption is used.

### Case 13 — Encrypted Token Storage, Raw Token Logged

**Risk?**

> Tokens can still leak via APM/log retention. Redaction is required at every layer.

### Case 14 — Principal Key Is Email

One email is used by accounts from two different issuers.

**Risk?**

> Cross-provider identity collision / cross-tenant token access. `(issuer, sub)` or a verified internal principal key is required.

### Case 15 — Backup Downloaded to a Laptop for Debugging

**Assessment?**

> Violates standard security policy for credential-bearing data. Use sanitized synthetic datasets and controlled isolated restores.

### Case 16 — User Logs Out of RP, Calendar Still Syncs

**Is this definitely a bug?**

> You cannot conclude that from logout alone. Clarify whether business logic expects disconnect/revoke or only ending the browser session. If policy dictates logout must halt sync, implement explicit lifecycle deletion/revocation.

### Case 17 — Key and Encrypted Backups Under the Same IAM Role

**Risk?**

> Compromising one role can be enough to download and decrypt all tokens. Separate permissions and audit access.

### Case 18 — Backup Job Succeeds, Restore Drill Fails to Decrypt

**Is the system DR-ready?**

> No. Backup success does not prove restoration success. Key lifecycle verification and restoration tests are required.

### Case 19 — 30-Day Retention Requested by Product

**Can this be applied blindly to every token?**

> No. Token types, active grants, AS rotation, consent, privacy, backups, and applicable laws must be evaluated. Never apply a fixed TTL that breaks authorized sessions.

### Case 20 — Testing the REST Interceptor Proves Storage Encryption?

`RestClient` sends the right Bearer access token; a developer concludes the database is secure.

**Conclusion?**

> No. Outbound Bearer header tests prove token usage, not JDBC column encryption, backup encryption, or IAM. Storage security integration tests are needed.

---

## 33. Production Deployment Checklist

### Classification and Storage

1. Have all places storing `OAuth2AuthorizedClient` been identified?
2. Are service-level storage and HTTP session repositories distinguished?
3. Is `InMemoryOAuth2AuthorizedClientService` being used unintentionally across multiple replicas?
4. Is `JdbcOAuth2AuthorizedClientService` used with the proper schema/migrations?
5. Are client registration secrets separated from authorized-client tokens?
6. Are separate policies defined for user-delegated vs. machine tokens?
7. Are identity/tenant/issuer keys sufficiently isolated?

### Credential Protection

8. Are token values encrypted at rest according to the threat model?
9. Is TLS enabled for DB/Redis/KMS/AS/RS?
10. Do backups have encryption and independent IAM?
11. Do key versions/DEKs/KEKs have lifecycle management and auditing?
12. Does AEAD/AAD bind record/tenant/token type?
13. Is there zero plaintext fallback when decryption fails?
14. Are tokens, client secrets, and session IDs excluded from logs/traces/metrics?
15. Are production DB copies sanitized before use in test/dev?

### Backup and Restore

16. Has it been decided whether token values are backed up based on RPO/RTO?
17. Do backups have integrity verification and restore rehearsals?
18. Are restores rehearsed with older key versions?
19. Is there a mechanism to quarantine stale/rotated refresh tokens?
20. Are bulk refreshes throttled/restricted right after restore?
21. Are revoked/deleted users from the post-snapshot ledger processed?
22. Are backup snapshots distinguished from replication?
23. Is there a recovery plan when the AS/KMS is unavailable?

### Retention and Deletion

24. Does retention account for access vs. refresh token lifecycles?
25. Does cleanup avoid deleting rows that still have valid refresh tokens?
26. Do disconnect/revoke/local delete have clear semantics?
27. Are backup expiry and crypto-erasure policies documented?
28. Is it guaranteed that restores do not resurrect deleted local tokens?
29. Are cross-tenant delete/read prevention controls tested?
30. Are organization-appropriate legal/privacy retention obligations documented?

### Concurrency and Operations

31. Is simultaneous multi-node refresh tested?
32. Are CAS/locking/fencing implemented if AS rotation requires them?
33. Are `invalid_grant` spikes and token issuance anomalies monitored?
34. Are downstream 401s distinguished from AS refresh failures?
35. Is there an incident response procedure if token backups/keys are compromised?

---

## 34. Final Decision Diagram

```text
Designing storage for OAuth2AuthorizedClient?
                    |
                    v
Is the authorized client a regenerable cache?
                    |
           +--------+---------+
           |                  |
          YES                NO
           |                  |
           v                  v
Consider omitting token   Need persistent encrypted store
values from backups       + RPO/RTO backup strategy
           |                  |
           +--------+---------+
                    |
                    v
Is data at rest protected?
                    |
       +------------+-------------+
       |                          |
      NO                         YES
       |                          |
       v                          v
Implement IAM/TLS/          Backup isolation, KMS,
encryption + redaction      key versions, integrity
                                  |
                                  v
                        Does token lifecycle use rotation?
                                  |
                         +--------+--------+
                         |                 |
                        YES               NO
                         |                 |
                         v                 v
                  Quarantine stale     Verify expiry,
                  restored refresh     revocation,
                  tokens               registration
                         |                 |
                         +--------+--------+
                                  |
                                  v
                      Any deleted/revoked grants
                      after backup timestamp?
                                  |
                         +--------+--------+
                         |                 |
                        YES               NO
                         |                 |
                         v                 v
                   Replay tombstones  Continue controlled
                   /remove rows       recovery
                         |                 |
                         +--------+--------+
                                  |
                                  v
                           Controlled resume
                                  |
                                  v
                       Monitor invalid_grant / 401 /
                       decrypt failures / reauth rate

If unsure a token is valid: do not use it blindly.
If unsure a record is allowed to exist: block use until verified.
```

### Key Principles to Remember

1. **`OAuth2AuthorizedClient` holds credentials**, not merely a harmless “cache.”
2. **`OAuth2AuthorizedClientService` and `OAuth2AuthorizedClientRepository` have different scopes**; know where data actually lives.
3. **`JdbcOAuth2AuthorizedClientService` provides persistence but does not automatically mean tokens are application-encrypted.**
4. **Backing up token values is an architectural choice.** When reauthorization is viable, omitting them reduces the attack surface.
5. **Refresh token rotation means old snapshots can hold invalid tokens and carry reuse-detection risks.** Never auto-refresh in bulk right after a restore.
6. **Access token expiry does not dictate the lifetime of the refresh token or the entire authorized-client record.**
7. **Local deletion does not automatically revoke tokens at the AS, and deleting from the primary DB does not automatically erase immutable backups.**
8. **The revocation/deletion ledger must be applied on restore**, otherwise backups can resurrect removed links.
9. **Application-level AEAD encryption, backup encryption, KMS/IAM, and TLS complement one another**, rather than replacing one another.
10. **Tenant/issuer/principal isolation and concurrency control** must be designed into storage, keys, and caches instead of expecting the default schema to solve everything.
11. **Testing restores, encryption/key rotation, retention, and invalid_grant** proves operational readiness; backup job success is only a necessary condition.
12. **When uncertain about authorization or credential validity, fail closed and require reauthorization** instead of reusing old tokens or weakening security.

### References

- [Spring Security 6.5 — OAuth2 Client Core Interfaces](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/client/core.html)
- [Spring Security 6.5 — OAuth2 Client Authorized Clients](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/client/authorized-clients.html)
- [Spring Security 6.5 — Security Database Schema / OAuth2 Client](https://docs.spring.io/spring-security/reference/6.5/servlet/appendix/database-schema.html)
- [Spring Security 6.5 — JdbcOAuth2AuthorizedClientService API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/JdbcOAuth2AuthorizedClientService.html)
- [Spring Security 6.5 — AuthorizedClientServiceOAuth2AuthorizedClientManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceOAuth2AuthorizedClientManager.html)
- [Spring Security 6.5 — Reactive OAuth2 Client Core](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/core.html)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [RFC 8705 — OAuth2 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 9449 — OAuth2 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [NIST SP 800-57 Part 1 — Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final)
- [NIST SP 800-53 Rev. 5 — Security and Privacy Controls](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final)
