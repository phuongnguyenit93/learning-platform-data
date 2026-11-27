# Migrating Schemas, Client Data, Consents, and Authorizations

> **Chapter: Upgrade and Migration.** This lesson belongs to the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, covering the design and operation of an OAuth 2.0/OpenID Connect Authorization Server using Spring Authorization Server. The focus is on upgrading the application or database version while preserving client configurations, consent decisions, authorization transactions, and token state. A proper migration must preserve the security semantics of the data, not merely make SQL statements succeed.

An Authorization Server stores multiple interrelated types of state. Clients are referenced by authorizations and consents; authorizations contain tokens along with metadata used for refresh, revocation, and introspection. Migrating each table independently, changing IDs, misinterpreting serialized data, or dropping still-valid tokens can cause the system to issue incorrect tokens, lose revocation capability, or expand previously granted permissions.

## 1. Migration Objectives and Scope

Migration in an Authorization Server typically involves two distinct tasks:

- **Schema migration:** changing database structure such as tables, columns, data types, indexes, constraints, and access permissions.
- **Data migration:** transforming existing records into the new structure or data model while preserving relationships and business state.

The two tasks are often related but are not interchangeable. Adding a new column does not automatically convert old data to new semantics. Conversely, copying data to a new database does not guarantee that the target schema is compatible with the JDBC mapper of the running Spring Authorization Server version.

Main data groups in this lesson:

| Data Group | Service/Repository | Examples |
|---|---|---|
| Client registry | RegisteredClientRepository | `client_id`, encoded secret, redirect URIs, grant types, scopes, client settings, token settings |
| Authorization | OAuth2AuthorizationService | principal, authorization code, access token, refresh token, ID token, device/user code, and flow-specific metadata |
| Consent | OAuth2AuthorizationConsentService | principal, registered client, and approved authorities/scopes |

Post-migration objectives:

1. Each client retains its exact identity, credentials, and approved policies.
2. Each retained authorization can be read and processed according to its pre-migration state.
3. Consents are neither lost, duplicated, nor accidentally granted additional scopes.
4. Relationships between authorizations/consents and registered clients remain valid.
5. All new instances use the same schema and the same data source.
6. The migration can be proven via counts, checksums, relational checks, and protocol tests.
7. A practical rollback plan exists if cutover fails.

## 2. Understanding the Data Model Before Making Changes

Spring Authorization Server provides three commonly used persistence abstractions:

- **RegisteredClientRepository:** finds and saves registered clients.
- **OAuth2AuthorizationService:** finds, saves, and removes authorizations along with token state.
- **OAuth2AuthorizationConsentService:** finds, saves, and removes principal consents for clients.

The default JDBC implementations commonly use these tables:

| Table | Role | Relationships to Preserve |
|---|---|---|
| oauth2_registered_client | OAuth client configuration | Internal client key referenced by authorizations and consents |
| oauth2_authorization | Authorization transactions and token state | Must reference the correct registered client; retains principal, tokens, and metadata |
| oauth2_authorization_consent | Consent decisions | Bound to registered client and principal |

Exact table names and column details must be cross-checked against the schema resources in the exact artifact/version in use. Do not treat the table names or structure of one version as an immutable contract across all versions.

### 2.1. Registered Client

A RegisteredClient record may contain:

- Internal record ID and the `client_id` used in the OAuth protocol.
- Encoded client secret if the client uses a shared secret.
- Client authentication methods and authorization grant types.
- Redirect URIs, post-logout redirect URIs, and scopes.
- Client settings, such as PKCE or consent requirements.
- Token settings, such as token lifetimes and refresh token rotation policy.

The client's internal ID is usually referenced by authorization and consent records. When migrating data, preserve the ID if possible. If mapping to new IDs is unavoidable, create a persistent mapping table and apply that mapping across all dependent records.

Do not regenerate client secrets just because you are migrating databases. Encoded secrets generally cannot be decrypted back to the original value. If you preserve the hash and the new PasswordEncoder can still verify the old hash, the client continues using its current secret. If the legacy algorithm or hash format is no longer supported, plan a secret rotation via an administrative workflow.

### 2.2. Authorization and Token State

OAuth2Authorization can store:

- Authorization ID, registered client ID, and principal name.
- Grant type and authorized scopes.
- Attributes needed to continue or validate the flow.
- Authorization code, access token, refresh token, ID token, user code, or device code depending on the grant.
- Issued-at, expires-at, token type, scopes, and metadata.
- Token state such as invalidated or consumption markers.

Not every authorization contains all of these tokens. The exact schema and data depend on the flow and version. Preserve the values that the target version needs to process still-valid tokens accurately.

Token values and metadata can be sensitive data. Database access, backups, staging exports, and intermediate files must be protected like secrets. Do not write tokens or authorization codes to logs for comparison.

### 2.3. Consent

Consent is typically bound to a registered client and principal pair. The authorities data represents the permissions the user approved. When migrating consents:

- Preserve the exact principal name and case-sensitivity rules.
- Preserve the exact registered client identity.
- Preserve the exact set of approved authorities.
- Do not automatically add scopes just because the new version supports new scopes.
- Do not turn revoked or deleted consents into active consents.

Consent is not synonymous with a specific authorization/token. Deleting a token does not automatically withdraw consent; deleting consent also does not guarantee already-issued JWTs are immediately invalidated. Migration must preserve these two types of state separately.

## 3. Identifying Source, Target, and Data Invariants

Before writing migration scripts, inventory both source and target databases:

| Item to Identify | Question |
|---|---|
| Application version | What are the current Spring Authorization Server and Spring Security versions? |
| Target version | What are the target dependencies and corresponding schema resources? |
| Database engine | PostgreSQL, MySQL, Oracle, SQL Server, or another engine? |
| Schema | Are there custom schemas, columns, indexes, triggers, or naming conventions? |
| Clients | How many clients, how many confidential/public clients, and which encoders do credentials use? |
| Authorizations | How many records are active, expired, invalidated, or in flight? |
| Consent | How are principal names and authorities normalized? |
| Tokens | Are there opaque tokens, JWTs, refresh tokens, device flows, or custom tokens? |
| Integrations | Are there resource servers, introspection, admin consoles, or jobs reading tables directly? |
| Downtime tolerance | Is a maintenance window available, or is near-zero-downtime cutover required? |

Define invariants before migrating:

- `client_id` values have no duplicates and do not change outside the approved plan.
- Post-migration client secrets are still verified by `PasswordEncoder`.
- Redirect URIs, grant types, authentication methods, and scopes are not unintentionally expanded.
- Every retained authorization references the right client and principal.
- Token values, lifetimes, scopes, and states are preserved if tokens continue to be accepted.
- Consent authorities do not grow beyond the set approved by the user.
- No orphaned authorizations or consents exist after migration.

Make these invariants acceptance criteria. Do not rely solely on row counts in the target table matching the source table.

## 4. Choosing a Migration Strategy

Choose a strategy based on the extent of schema changes, data volume, and allowed downtime.

| Strategy | When Appropriate | Advantages | Risks/Notes |
|---|---|---|---|
| In-place schema migration | Database stays the same, schema changes are minor and compatible | Minimal data copying | DDL rollback can be hard; requires backups and compatible migrations |
| Offline export/import | Maintenance window available and moderate data volume | Easy snapshot control and verification | Service must stop writes during migration |
| Shadow database + backfill | New target database or large data volume | Can prepare and verify before cutover | Must catch up with changes occurring during backfill |
| Replication/CDC | Low downtime required and supporting infrastructure available | Continuous delta synchronization | Complex ordering, deletes, transactions, and schema mapping |
| Application-level migration | Complex format/model transformations needed | Uses domain models and serializers of the exact versions | Requires custom utility, compatibility control, and performance tuning |

For an Authorization Server, offline migration with a maintenance window is usually the easiest to prove correct. If online migration is required, use a well-designed backfill and delta-sync workflow. Do not implement ad-hoc dual writes to two databases: a write succeeding on source but failing on target creates divergent state.

~~~mermaid
flowchart TD
    A[Inventory source and target] --> B[Choose migration strategy]
    B --> C[Backup and rehearse]
    C --> D[Prepare target schema]
    D --> E[Copy or transform client records]
    E --> F[Copy authorization and consent]
    F --> G[Validate counts, relations and security invariants]
    G --> H{Validation passes?}
    H -->|No| I[Stop cutover and reconcile]
    I --> E
    H -->|Yes| J[Freeze writes and apply final delta]
    J --> K[Switch application to target]
    K --> L[Run protocol smoke tests]
    L --> M{Smoke tests pass?}
    M -->|No| N[Rollback using runbook]
    M -->|Yes| O[Monitor and close migration]
~~~

## 5. Schema Migration with Flyway or Liquibase

Spring Authorization Server ships sample SQL schemas inside the artifact matching the dependency version. The resources are commonly named:

- oauth2-registered-client-schema.sql
- oauth2-authorization-schema.sql
- oauth2-authorization-consent-schema.sql

Extract the schemas from the exact target version being deployed, compare them with the current schema, and turn differences into versioned migrations. Do not edit resources directly inside dependency libraries, and do not assume the new schema is merely the old schema plus a few columns.

### 5.1. Migration Creation Process

1. Capture the current schema via migration history or schema diff.
2. Extract sample schemas from the exact target artifact.
3. Compare tables, columns, data types, lengths, nullability, indexes, and constraints.
4. Determine which changes are DDL and which require data transformation.
5. Write versioned migrations, review them, and run them on a database copy.
6. Measure execution time, locks, temporary storage, and replication impact.
7. Verify whether old and new application versions can coexist during a rolling deployment.

### 5.2. Expand-Migrate-Contract

For systems requiring rolling deployment, use a three-phase strategy:

**Expand:** add new tables/columns/indexes in a backward-compatible way. Old code can still run against the expanded schema.

**Migrate:** backfill data and deploy new code capable of reading the new structure. If transitioning gradually, clearly define the authoritative data source at each stage.

**Contract:** remove old columns/tables only after no node or job uses them, data has been verified, and the rollback window has closed.

Do not drop columns in the same deployment while old instances are still running. Doing so can break old nodes mid-rolling deployment.

### 5.3. Data Types and Indexes

Pay special attention to:

- Columns storing attributes, metadata, settings, or token values may need large lengths.
- Some databases distinguish text, CLOB, and JSON types and limit indexes on long columns.
- Timestamp/time zone types must agree on interpretation and precision.
- Unique constraints on `client_id` and consent keys must match collation/case sensitivity.
- Indexes supporting token and client lookups must be preserved or created according to the schema resources.
- Do not change charsets/collations in a way that causes two distinct `client_id` values to compare equal.

Custom schemas must be tested against the exact production database engine. H2 or another dialect is insufficient to prove DDL will behave identically in production.

## 6. Migrating RegisteredClient Data

Registered clients are usually the first data group to migrate because authorizations and consents reference them.

### 6.1. Preserving Client Identity

Prioritize preserving:

- Internal ID.
- `client_id`.
- Client name.
- Encoded client secret.
- Authentication methods and grant types.
- Redirect URIs, post-logout redirect URIs, and scopes.
- Client settings and token settings.

If the internal ID must change, build a complete mapping:

| Source client ID | Target client ID | client_id |
|---|---|---|
| old-client-001 | new-client-001 | web-portal |
| old-client-002 | new-client-002 | orders-service |

The mapping must be stored durably in a controlled migration workspace or staging table, not only in script memory. Use this mapping when migrating authorizations and consents.

### 6.2. Preserving Client Secrets

Client secrets are stored as encoded values. You need to:

1. Identify the PasswordEncoder and hash format at the source.
2. Copy the encoded value verbatim if the target version can still verify it.
3. Run checks with a controlled set of test credentials using `PasswordEncoder.matches`.
4. Do not log raw secrets or encoded secrets.
5. If the old encoder is no longer supported, plan a secret rotation and coordinate with client owners.

Password/client secret hashes are one-way. You cannot recover the raw secret to re-encode it with a new encoder. Changing encoders cannot be completed with a single SQL statement.

If using `DelegatingPasswordEncoder`, check the hash prefix and encoder ID. Do not strip prefixes or alter hash strings by guesswork.

### 6.3. Settings and Redirect URIs

Client settings and token settings may be stored as JSON/serialized representations. Use serializers/mappers matching the source and target versions when formats change. Do not run bulk JSON string replacements without verifying the structure and meaning of every property.

Verify the exact set of redirect URIs. A missing URI can break login callbacks; an unplanned URI can widen the redirect surface. Do not automatically normalize schemes, hosts, paths, or trailing slashes during migration without an approved rule.

### 6.4. Client Registry Validation

After migrating:

- Client counts by public/confidential type match the inventory.
- `client_id` values have no duplicates.
- All grant types and authentication methods belong to the approved set.
- Redirect URIs and scopes match the source snapshot.
- Every encoded secret can be verified by the target encoder using controlled test credentials.
- No extra clients outside the inventory or duplicate clients exist.

## 7. Migrating OAuth2Authorization Data

This is usually the riskiest part because it holds protocol and token state.

### 7.1. Preserving Relationships and State

For each migrated authorization, verify:

- Authorization ID.
- Registered client ID after applying mapping.
- Principal name and grant type.
- Authorized scopes.
- Attributes and metadata.
- Token values, issued-at, expires-at, type, scopes, and invalidated status.

When migrating to another database, do not copy the authorization table first and handle clients later. The target must already contain the clients referenced by authorizations. You can follow the order of clients first, authorizations second, consents last, or follow actual schema constraints.

### 7.2. Serialized Attributes and Metadata

Attributes may contain data serialized using Spring Security or Spring Authorization Server classes. Dependency upgrades can change classes, type aliases, or serialization formats.

- Determine the actual format of source data.
- Read using a version/serializer compatible with the source.
- Convert to the target representation via an explicit mapping.
- Retain unrecognized fields if the target schema and application require them; do not drop them just to make the migration pass.
- Do not deserialize untrusted data using arbitrary Java native serialization.
- Test with representative data covering all grant/token types in use.

If an authorization attribute type cannot be migrated safely, explicitly decide whether to keep compatibility via an adapter or proactively invalidate the affected authorizations. Do not silently drop fields and keep issuing tokens.

### 7.3. Handling Still-Valid Tokens

Classify authorizations before migration:

| Status | Typical Handling |
|---|---|
| Expired authorization/token | Can be skipped or kept per retention/audit policy |
| Invalidated or revoked authorization/token | Preserve revocation status if needed for audit; never restore to active |
| Active authorization code | Migrate only if full metadata, one-time state, and expiration are preserved; otherwise let in-flight flows finish before maintenance or force clients to restart |
| Active access token | Preserve token value and metadata if continuing to accept tokens |
| Active refresh token | Preserve rotation/replay state and authorization linkage; test refresh after cutover |
| Pending device/user code | Migrate full state/expiry if supported; otherwise expire cleanly and require clients to start a new flow |

Do not issue new tokens simply to replace table values without updating clients/resource servers. Do not alter token values, token hashes, or metadata in a way that makes existing tokens unresolvable.

For JWT access tokens, resource servers can continue verifying signatures independently of the database until tokens expire. If the migration changes the issuer or signing key, plan legacy token verification, publish the old JWK during the transition period, or accept revocation/re-login per published policy.

For opaque tokens, lookup usually depends on the authorization store. If records/token values are not migrated accurately, resource servers may receive inactive results after cutover.

### 7.4. Deciding Whether to Keep or Purge Old Authorizations

Not every historical authorization needs to be migrated. Expired records can be purged per retention policy if no longer needed for audit or operations. However, the decision must be made before migration:

- Define the time threshold and statuses to keep.
- Retain audit evidence as required.
- Do not delete active tokens merely to save space.
- Do not turn revoked records into active ones.
- Record counts and reasons for excluded records.

If choosing not to migrate still-valid authorizations, communicate the impact in advance: existing sessions or tokens may require re-login/re-authorization. This is a product and security decision, not an implicit ETL side effect.

## 8. Migrating OAuth2AuthorizationConsent

Consents are usually fewer in number than authorizations, yet they directly affect permissions users have approved.

### 8.1. Mapping Clients and Principals

Each consent must map:

- `registered_client_id` to the target internal client ID.
- `principal_name` following the same user identification rules.
- `authorities` preserving the exact approved permission set.

If the system changes user IDs, tenant IDs, or canonicalization, a formal mapping is required. Do not automatically lowercase principal names if the identity store is case-sensitive or multi-tenant.

### 8.2. Avoiding Consent Expansion

When the new version introduces new scopes, do not automatically add those scopes to existing consents. Users must be prompted again, or consents must be updated according to approved policy.

A useful check is comparing the authority set before and after:

- No authorities are lost outside approved changes.
- No new authorities appear without valid consent.
- Every consent points to an existing client.
- No duplicate records exist for the same client/principal pair.

### 8.3. Consents and Issued Tokens

If a consent is withdrawn or changed during migration, decide separately how to handle authorizations already issued from that consent. You may need to revoke refresh tokens, mark authorizations invalidated, or require introspection per policy. Deleting a consent row alone does not automatically perform these actions.

## 9. Using Service APIs or Direct SQL/ETL?

There is no single approach suited to every migration.

| Approach | When Appropriate | Aspects to Control |
|---|---|---|
| Versioned SQL migration | Schema and data formats are compatible; changes are mostly DDL/SQL | Vendor dialect, transactions, locking, and serialized data |
| Table-based ETL | Database migration or explicit relational mapping needed | ID mapping, table order, batching, retries, and reconciliation |
| Application-level migration | Domain model/serialized attribute conversion needed | Serializers for both versions, service APIs, and token semantics |
| Export/import via neutral format | Source and target differ by major version | Define intermediate format, versioning, encoding, and full field validation |

`RegisteredClientRepository`, `OAuth2AuthorizationService`, and `OAuth2AuthorizationConsentService` are useful runtime abstractions, but they do not automatically provide a cross-version migration protocol. If using service APIs to import data, ensure objects are constructed using the model/serializer of the target version and test thoroughly before running in production.

With direct ETL, avoid `INSERT SELECT *` across schemas of different versions. Always list columns explicitly and map each field. For serialized data, understand the representation before migrating; never alter blobs/JSON with blind string operations.

### 9.1. Batched ETL Workflow

A migration job can execute in cycles:

~~~text
1. Read a deterministically ordered batch from the source.
2. Validate the record and required relationships.
3. Apply client/principal/field mappings.
4. Write to staging or target tables within a short transaction.
5. Record the checkpoint and processed count.
6. Commit, then advance to the next batch.
7. On retry, identify already-imported records to avoid duplicates.
~~~

Choose batch size based on latency, transaction log, locks, and recovery needs. Do not hold a single transaction across millions of records unless the database is designed for it.

The migration job must be idempotent or have a clear resume mechanism. Use the source primary key and migration version to identify processed records. Do not rely solely on processed row counts because a batch may commit before the job loses connection and records its checkpoint.

## 10. Cutover Plan with Downtime

This is the easiest approach to control when a maintenance window can be scheduled.

### 10.1. Before Maintenance

1. Inventory clients, authorizations, consents, and token state.
2. Take a consistent backup and test restoring it in an isolated environment.
3. Prepare the target schema using versioned migrations.
4. Dry-run the full data migration on a production-like snapshot.
5. Record execution time, storage size, record counts, and validation results.
6. Prepare endpoint/maintenance pages and notify client owners.
7. Prepare a rollback runbook with named owners and trigger conditions.

### 10.2. During Maintenance

1. Stop accepting new authorization/token requests or route traffic to a maintenance response.
2. Stop administrative jobs, client provisioning, and background writers.
3. Wait for in-flight requests to finish within a defined timeout.
4. Take a final snapshot or consistent backup.
5. Run schema migration and data migration.
6. Run reconciliation and relational checks.
7. Point application configuration to the target database.
8. Run smoke tests before reopening traffic.

### 10.3. After Cutover

- Ramp up traffic gradually if the platform supports it.
- Monitor login errors, `invalid_client`, `invalid_grant`, `invalid_scope`, and introspection errors.
- Test refresh tokens and consents using test clients.
- Monitor database pools, slow queries, and replication.
- Retain source backups and migration logs per retention policy.
- Close the rollback window only after owners accept operational metrics.

## 11. Online Migration and Low-Downtime Cutover

Online migration is suitable when writes cannot be stopped for long periods, though it is significantly more complex.

A typical workflow includes:

1. Create a target schema compatible with the new application version.
2. Take a consistent snapshot at time T0.
3. Backfill data from the snapshot to the target.
4. Synchronize changes after T0 via CDC, transaction logs, or a purpose-built outbox mechanism.
5. Continuously compare source and target counts and state.
6. Prepare the application to read target data in staging.
7. At cutover time, briefly lock writers on the source.
8. Apply the final delta, confirm watermarks, and run reconciliation.
9. Switch traffic to the target.
10. Monitor and allow writes in only one authoritative location.

### 11.1. Ordering and Deletes

CDC must preserve required ordering. For example, a client is created before authorizations referencing that client. If a delete event arrives before an insert event due to improper partitioning/ordering, target data can become corrupted.

You must handle:

- Inserts, updates, and deletes.
- Client ID mapping changes.
- Revoked/invalidated token state.
- Consent removal.
- Retries and duplicate events.
- Multi-table transactions.

### 11.2. Avoid Uncontrolled Dual-Writes

If the application writes concurrently to both source and target databases without distributed transactions or an outbox, the following can happen:

- Source commits, target fails.
- Target commits, source times out even though it actually committed.
- Both stores process the same request in different orders.
- Revocation succeeds in one store while refresh still succeeds in the other.

Only use dual-writes when you have idempotency, reconciliation, retries, and an explicit authoritative source. With token data, even minor divergence can affect access control.

## 12. Validation and Reconciliation

Validation needs multiple layers. Matching counts is only the first step.

### 12.1. Comparing Counts

Example overview queries on the default JDBC schema:

~~~sql
SELECT COUNT(*) FROM oauth2_registered_client;
SELECT COUNT(*) FROM oauth2_authorization;
SELECT COUNT(*) FROM oauth2_authorization_consent;
~~~

Compare by data type and status if the schema permits. If expired records were filtered out, document the filter condition and excluded count.

### 12.2. Checking Relationships

Check that authorizations reference existing registered clients:

~~~sql
SELECT a.registered_client_id
FROM oauth2_authorization a
LEFT JOIN oauth2_registered_client c
    ON c.id = a.registered_client_id
WHERE c.id IS NULL;
~~~

Check that consents reference existing clients:

~~~sql
SELECT s.registered_client_id
FROM oauth2_authorization_consent s
LEFT JOIN oauth2_registered_client c
    ON c.id = s.registered_client_id
WHERE c.id IS NULL;
~~~

Verify column names against the actual schema of the version in use. The expected result is zero orphaned records, unless the migration has a documented mapping/exception.

### 12.3. Checksums and Semantic Comparison

For non-sensitive or protected data, compute checksums across stable field groups:

- Client: `client_id`, redirect URIs, grant types, scopes, and settings.
- Authorization: ID, client mapping, principal, grant type, token timestamps, and status.
- Consent: client mapping, principal, and authority set.

Canonicalize collection ordering before hashing to avoid differences caused by storage order. Do not include raw secrets/tokens in reports or checksum logs. For sensitive values, a separately managed HMAC key can be used for comparison without exposing data.

### 12.4. Protocol Smoke Tests

After data has been migrated:

1. Confidential clients authenticate successfully with their current secret.
2. Public clients complete authorization code + PKCE.
3. Authorization codes can only be exchanged once.
4. Existing consents are applied accurately.
5. Refresh tokens behave according to the rotation policy.
6. Token revocation is reflected via introspection if the flow uses it.
7. Resource servers verify JWTs issued before and after migration per key/issuer policy.
8. One instance writes data and another instance can read/continue processing it.

Do not use production user credentials or real tokens in tests. Create test clients/principals with narrow scope and limited lifetime.

## 13. Rollback and Recovery

Rollback is not as simple as running reverse SQL migrations. Once the new application starts writing data, the source database may already be stale.

### 13.1. Before Cutover

If validation fails before opening traffic, halt the migration, keep the source intact, wipe or restore the target database from snapshot, and fix the ETL. No traffic switch is needed if the source has not been modified.

### 13.2. After Cutover

Decide the rollback strategy before cutover:

- **Application rollback:** feasible only if the new schema/data remain compatible with the old version.
- **Database rollback:** requires a pre-cutover snapshot or backup; new writes after cutover may be lost if restoring the old source.
- **Forward fix:** fixing issues on the target database may be safer if new transactions have already occurred.
- **Reverse replication:** feasible only if reverse synchronization was designed and tested beforehand.

If authorizations, token refreshes, revocations, or consent updates have occurred on the target, do not switch traffic back to the old source without synchronizing those changes. In particular, a refresh token that was rotated or revoked on the target must never return to active status due to rollback.

The runbook must specify rollback trigger thresholds, decision makers, the authoritative data source, and how to handle tokens/consents created during the cutover window.

## 14. Security and Operations During Migration

- Use a least-privilege database account for the migration job.
- Protect backups, export files, staging tables, and temporary directories.
- Encrypt data in transit and at rest per environment policy.
- Never log raw passwords, client secrets, authorization codes, access tokens, refresh tokens, or session cookies.
- Restrict access to principal and consent data.
- Never copy production dumps onto laptops or public CI artifacts.
- Delete or sanitize temporary files per retention policy after sign-off.
- Audit who ran the migration, which version, which snapshot, and what outcome.
- Use a migration lock or mechanism ensuring only one migration job runs at a time.
- Monitor lock duration, replication lag, transaction logs, and database storage capacity.

If sample data is needed to develop migrations, prefer synthetic or anonymized data. Anonymization must preserve enough relational integrity to test mappings and constraints.

## 15. Common Failure Scenarios

| Symptom | Possible Cause | Remediation |
|---|---|---|
| Client exists but secret authentication fails | Encoded secret altered, encoder prefix stripped, or target encoder does not support old hash | Safely compare encoded values, verify PasswordEncoder, and plan rotation |
| Authorization not found after migration | ID/token value altered or lookup field not migrated | Check authorization ID, token value, and target version's mapper |
| Authorization points to non-existent client | Missing client migration or wrong ID mapping | Migrate clients first, check orphans and mapping table |
| Users prompted for consent again | Consent dropped, principal name differs, or authority mapping wrong | Compare principal/client mappings and authority sets |
| Broader scopes granted than before | Migration added new scopes to old consents | Restore approved permission sets and require new consent per policy |
| Old refresh token works again | Invalidated/rotation state lost or rolled back to old snapshot | Lock traffic, verify token state, and revoke affected credentials |
| Opaque token becomes inactive | Authorization/token row or token value not migrated accurately | Inspect token lookups and metadata in the authorization store |
| Old JWT fails verification | Issuer changed or old public key removed too early | Maintain JWK overlap or enforce controlled re-authentication policy |
| Repeated migration run creates duplicates | Non-idempotent job or unreliable checkpoint | Use source key/version markers and unique constraints |
| Schema migration hangs | Large locks, index builds, or overly long transactions | Batch operations and choose database-appropriate online index strategies |
| Old nodes fail after expand | Migration not backward compatible | Restore compatible schema or roll out synchronously per runbook |
| Counts match but flows fail | Corrupted serialized data, relationships, or token metadata | Add semantic validation and protocol smoke tests |

## 16. Migration Test Matrix

| # | Scenario | Expected Result |
|---|---|---|
| 1 | Migrate confidential client with encoded secret | Client authenticates with existing secret |
| 2 | Migrate public client | Client ID, redirect URIs, grants, and PKCE policy preserved |
| 3 | Migrate client with multiple redirect URIs/scopes | Target value set matches source snapshot |
| 4 | Migrate client settings/token settings | Policies are not relaxed unintentionally |
| 5 | Migrate still-valid authorization code | Code is single-use only or cleanly expired per plan |
| 6 | Migrate active access token | Token handled properly per format and issuer |
| 7 | Migrate rotated refresh token | Old token stays invalidated; new token works |
| 8 | Migrate revoked token | Revoked status is not restored |
| 9 | Migrate principal consent | Client, principal, and authorities preserved |
| 10 | Principal name with case/tenant differences | Mapping does not unintentionally merge two principals |
| 11 | Authorization referencing unmapped client | Migration halts or routes record to exception queue |
| 12 | ETL stops mid-batch | Resumes without duplicates or missed records |
| 13 | ETL reruns after commit but before checkpoint | Already-processed records are safely identified |
| 14 | Serialized attributes from older version | Read/converted or rejected in a controlled manner |
| 15 | Cutover to new database | New instances read clients, authorizations, and consents |
| 16 | Target database unavailable | Authorization Server does not grant access via local fallback |
| 17 | Rollback after new refreshes/revocations | Rotated/revoked tokens are never restored to active |
| 18 | Old JWT during key transition | Resource server verifies per overlap policy |
| 19 | Opaque token after cutover | Introspection returns active/inactive matching true state |
| 20 | Rolling deployment with expanded schema | Old and new nodes operate together during allowed window |

### 16.1. Validation Query Examples

The following queries are examples for the default JDBC schema; adjust column names if your organization customized the schema:

~~~sql
-- Client IDs must be unique.
SELECT client_id, COUNT(*)
FROM oauth2_registered_client
GROUP BY client_id
HAVING COUNT(*) > 1;

-- Authorizations must reference an existing client.
SELECT COUNT(*)
FROM oauth2_authorization a
LEFT JOIN oauth2_registered_client c
    ON c.id = a.registered_client_id
WHERE c.id IS NULL;

-- Consents must reference an existing client.
SELECT COUNT(*)
FROM oauth2_authorization_consent s
LEFT JOIN oauth2_registered_client c
    ON c.id = s.registered_client_id
WHERE c.id IS NULL;
~~~

The expected result is zero duplicate `client_id` values and zero orphaned authorizations/consents. These queries do not verify token metadata or consent semantics; combine them with service/API checks and protocol tests.

## 17. Production Checklist

- [ ] Source and target Spring Authorization Server versions identified.
- [ ] Schema resources extracted from the exact target artifact.
- [ ] Clients, authorizations, consents, tokens, and custom extensions inventoried.
- [ ] Invariants and acceptance criteria defined.
- [ ] Consistent backup taken and restore tested.
- [ ] Schema migrations versioned and reviewed.
- [ ] DDL tested on the exact database engine/version.
- [ ] Client IDs and ID mappings preserved.
- [ ] Encoded client secrets preserved or rotation plan in place.
- [ ] Redirect URIs, grant types, authentication methods, and scopes compared.
- [ ] Serialized settings, attributes, and token metadata handled knowingly.
- [ ] Authorization codes, access tokens, refresh tokens, and revocation states classified.
- [ ] Consents preserve principals and authorities; no automatic scope expansion.
- [ ] ETL supports batching, checkpoints, retries, and idempotency.
- [ ] Orphan, duplicate, count, and semantic checksum checks executed.
- [ ] Protocol smoke tests executed across multiple instances.
- [ ] Issuer/signing key/JWK overlap plan ready if changed.
- [ ] Maintenance/cutover plan and rollback runbook in place.
- [ ] No dual-writes without reconciliation mechanisms.
- [ ] Logs and temporary files do not expose credentials/tokens.
- [ ] Designated owner assigned to decide cutover and close the rollback window.

## 18. Self-Assessment Questions

1. How does schema migration differ from data migration?
2. Why must schema resources be taken from the exact target Spring Authorization Server version?
3. Why must `RegisteredClient` records be migrated before authorizations and consents?
4. Why should the internal ID of `RegisteredClient` be preserved?
5. Can a hashed client secret be decrypted to re-encode with a new encoder?
6. When is rotating a client secret necessary instead of copying the encoded value?
7. What types of tokens and metadata can be stored in `OAuth2Authorization`?
8. Why must serialized attributes be processed with a compatible serializer?
9. When can expired authorizations be purged?
10. What happens if a migration loses the invalidated state of a refresh token?
11. Why must consents not be automatically expanded when new scopes are added?
12. When should you use SQL migration, ETL, or application-level migration?
13. Why is `INSERT SELECT *` dangerous between two schemas of different versions?
14. How must online migration handle ordering, duplicate events, and deletes?
15. Why can dual-writes cause revocation state divergence?
16. Are matching row counts sufficient to prove a migration is correct?
17. How are JWTs and opaque tokens affected differently when migrating the authorization store?
18. Why does post-cutover rollback require synchronizing refresh/revocation state?
19. How does expand-migrate-contract help rolling deployments?
20. Which smoke tests should run before reopening traffic?

## References

- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient`, `OAuth2Authorization`, consent models, and services/repositories.
- [Spring Authorization Server — Getting Started](https://docs.spring.io/spring-authorization-server/reference/getting-started.html): foundational configuration and components of Authorization Server.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): authorization, token, introspection, and revocation endpoints.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): how to configure Authorization Server components.
- [Spring Framework — JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html): `JdbcTemplate`, `JdbcOperations`, and database access.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): transaction boundaries and `@Transactional`.
- [Flyway Documentation](https://documentation.red-gate.com/flyway): versioned schema migrations and migration history.
- [Liquibase Documentation](https://docs.liquibase.com/): managing changesets, schemas, and data migrations.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT validation and JWK Sets.
