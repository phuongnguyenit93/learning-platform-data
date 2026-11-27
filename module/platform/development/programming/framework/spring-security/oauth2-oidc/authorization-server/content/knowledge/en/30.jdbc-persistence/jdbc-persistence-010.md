# Cleaning Up Expired Authorizations, Backups, and Data Recovery

Spring Authorization Server stores authorizations, tokens, and consents in a database when the application uses JDBC persistence. Over time, the `oauth2_authorization` table can accumulate records holding expired authorization codes, access tokens, refresh tokens, ID Tokens, device codes, or user codes. Without a retention policy, data grows continuously, backups swell, and operational queries become harder to predict.

Data cleanup requires understanding the exact storage structure: **a single `oauth2_authorization` row can contain multiple tokens belonging to the same authorization**. An expired access token does not mean the refresh token has also expired; an expired authorization code does not mean the access token issued afterward has expired. Deleting rows based on a single `expires_at` column can wipe still-valid tokens or break refresh capability.

Alongside cleanup, an Authorization Server needs consistent backups across JDBC data, configuration, and signing keys. Restoring an old database without signing keys, client registrations, or revocation data can prevent the issuer from verifying tokens, disable clients, or cause previously revoked tokens to reappear.

This lesson belongs to the **JDBC Persistence** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, focusing on designing, configuring, securing, testing, and operating an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in a Spring Boot application.

After this lesson, you will be able to:

- Describe the key JDBC tables and the relationships between authorizations, consents, and registered clients.
- Distinguish the lifetimes of individual tokens stored inside an authorization.
- Design safe cleanup per token and across the entire authorization.
- Use retention grace periods, batched deletes, transactions, and `SKIP LOCKED`.
- Avoid deleting authorizations that still hold active refresh tokens or other live tokens.
- Establish retention policies for consents, registered clients, and audits independently from token cleanup.
- Take consistent backups of the database, WAL/PITR, signing keys, secrets, and issuer configuration.
- Restore into an isolated environment, verify data, and control the risk of rolling back revocations.
- Practice testing cleanup, backup/restore, and disaster recovery.

## 1. What Data Does JDBC Persistence Store?

Spring Authorization Server provides these core JDBC persistence services:

| Service | Default table | Data |
| --- | --- | --- |
| `JdbcRegisteredClientRepository` | `oauth2_registered_client` | Client IDs, encoded secrets, redirect URIs, grant types, scopes, authentication methods, and client settings. |
| `JdbcOAuth2AuthorizationService` | `oauth2_authorization` | Authorizations, principals, attributes, and related tokens. |
| `JdbcOAuth2AuthorizationConsentService` | `oauth2_authorization_consent` | Consents/authorities approved by users for clients. |

These services operate against the JDBC schemas provided by Spring Authorization Server. In production, schemas are typically managed via Flyway, Liquibase, or an equivalent migration tool. Use the schema matching your exact dependency version; never arbitrarily drop columns or alter data types required by row mappers/converters.

### 1.1. The oauth2_authorization Table

The `oauth2_authorization` table holds one row per authorization. Depending on grant type and flow state, that row can store:

- authorization code;
- access token;
- OIDC ID Token;
- refresh token;
- user code;
- device code;
- issued-at, expires-at, and metadata for each token;
- principal name, client registration ID, grant type, authorized scopes, and attributes.

Token columns typically have dedicated timestamp pairs, such as `access_token_issued_at`, `access_token_expires_at`, `refresh_token_issued_at`, and `refresh_token_expires_at`. Tokens unused in a flow may have `NULL` in their corresponding columns.

### 1.2. One Authorization Does Not Mean One Token

Authorization Code flow example:

~~~mermaid
flowchart TD
    A["oauth2_authorization row"] --> C["Authorization Code"]
    A --> AT["Access Token"]
    A --> RT["Refresh Token"]
    A --> IDT["OIDC ID Token"]
    C --> CE["Code expires after a few minutes"]
    AT --> AE["Access Token expires"]
    RT --> RE["Refresh Token may still be valid"]
    IDT --> IE["ID Token has its own lifetime"]
~~~

A row may contain an expired authorization code and an expired access token while its refresh token remains valid. If cleanup deletes the entire row based on `authorization_code_expires_at` or `access_token_expires_at`, the client loses a still-usable refresh token.

**Rule:** lifetimes must be evaluated per token; delete an entire authorization only when every potentially usable token in that row has expired or been cleared per retention policy.

### 1.3. Consents and Registered Clients Have Different Lifecycles

`oauth2_authorization_consent` is not a token cache and does not share expiration semantics with access/refresh tokens. Consents can outlive many authorizations. Deleting expired authorizations does not automatically mean deleting consents.

`oauth2_registered_client` holds client configurations. One client can have many authorizations and consents. Deleting a client registration while its tokens/authorizations are still valid can leave the server unable to resolve the client configuration needed to process those authorizations.

Never run a blanket `DELETE` across all three tables based on token expiration dates.

## 2. Defining Exact Expiration Conditions

### 2.1. Using Each Token's Expiration Timestamp

| Token | Expiration column | Consequence upon expiry |
| --- | --- | --- |
| Authorization Code | `authorization_code_expires_at` | Expired code cannot be exchanged for tokens. |
| Access Token | `access_token_expires_at` | Resource Server must reject expired tokens during validation. |
| OIDC ID Token | `oidc_id_token_expires_at` | Client must not use an expired ID Token as a fresh authentication assertion. |
| Refresh Token | `refresh_token_expires_at` | Expired refresh token cannot be used to obtain new access tokens. |
| User Code | `user_code_expires_at` | Expired user code cannot complete device authorization. |
| Device Code | `device_code_expires_at` | Expired device code cannot be exchanged for tokens. |

Exact column names must be verified against the SQL schema bundled with the active Spring Authorization Server version. If the application has custom token types or custom columns, cleanup must understand those columns too.

### 2.2. NULL Does Not Always Mean Expired

In the standard schema, unissued tokens typically have `*_value IS NULL`. When a token value is present while `*_expires_at IS NULL`, cleanup must not infer that the token has expired. Retain the record until explicit rules exist for that token type.

A safe condition looks like:

~~~sql
(token_value IS NULL
 OR (token_expires_at IS NOT NULL AND token_expires_at < :cutoff))
~~~

This condition means:

- no token value present: this component does not block cleanup;
- token value present and expiry is past cutoff: the token is eligible for cleanup per retention policy;
- token value present with no expiry: retain it to avoid accidental deletion.

### 2.3. Using a Grace Period

Do not necessarily delete the instant the clock passes `expires_at`. An extra retention buffer, such as 24 hours or 7 days depending on policy, helps with:

- incident investigation and auditing;
- in-flight request processing;
- retries from clients experiencing clock skew;
- data reconciliation and operational support;
- ensuring all nodes share consistent time interpretation.

Let the cleanup timestamp be `cutoff = current_time - retention_grace_period`. Consider a token eligible for cleanup only when `expires_at < cutoff`.

A grace period is an operational policy, not a replacement for endpoint token expiry checks. Expired access tokens must still be rejected even while the row remains in the database.

## 3. Two Cleanup Strategies

| Strategy | Behavior | When suitable |
| --- | --- | --- |
| Delete entire authorization once all tokens expire | Delete row only when every token value is absent or expired past cutoff. | Simple; keeps tokens in the same authorization until none remain usable. |
| Clear expired tokens individually, then delete empty rows | Set expired token columns to `NULL`, keeping valid tokens; delete row once no token values remain. | Reduces retention of old tokens when an authorization still holds an active refresh token. |

No single cleanup schedule fits every system. Choose a strategy based on retention requirements, investigation needs, and the behavior of your `JdbcOAuth2AuthorizationService` version.

### 3.1. When Should You Clean Up Individual Tokens?

Suppose an authorization has an access token that expired yesterday, an ID Token that expired yesterday, and a refresh token valid for 20 more days. If you only delete the entire row once all tokens expire, the old access token and ID Token remain in the database for 20 extra days. If policy requires minimizing retention of expired bearer tokens, clear expired token fields individually while retaining the refresh token and authorization parts needed for refresh flows.

When clearing individual tokens, update `value`, `issued_at`, `expires_at`, `metadata`, and related token-descriptor columns together. Never null out only `*_value` and leave stale metadata that could mislead row mappers or operational queries.

## 4. Safe Cleanup SQL on PostgreSQL

The examples below use PostgreSQL and column names from the standard JDBC schema. For MySQL, SQL Server, or other engines, adjust batch/locking syntax and inspect execution plans. Always verify against actual schema migrations before running.

### 4.1. Cleaning Up Expired Authorization Codes

~~~sql
UPDATE oauth2_authorization
SET authorization_code_value = NULL,
    authorization_code_issued_at = NULL,
    authorization_code_expires_at = NULL,
    authorization_code_metadata = NULL
WHERE authorization_code_value IS NOT NULL
  AND authorization_code_expires_at IS NOT NULL
  AND authorization_code_expires_at < :cutoff;
~~~

This statement clears only authorization code data expired past `cutoff`. Access tokens, refresh tokens, and other tokens in the same row remain intact.

An expired authorization code cannot be exchanged for new tokens, though keeping its metadata during the grace period can aid investigating code replay or client retries. Pick cleanup timing suited to operational needs.

### 4.2. Cleaning Up Expired Access Tokens

~~~sql
UPDATE oauth2_authorization
SET access_token_value = NULL,
    access_token_issued_at = NULL,
    access_token_expires_at = NULL,
    access_token_metadata = NULL,
    access_token_type = NULL,
    access_token_scopes = NULL
WHERE access_token_value IS NOT NULL
  AND access_token_expires_at IS NOT NULL
  AND access_token_expires_at < :cutoff;
~~~

Do not clear refresh tokens in this statement. While a refresh token remains valid, the authorization row is still required so refresh flows can load the authorization and validate the refresh token.

### 4.3. Cleaning Up Expired Refresh Tokens

~~~sql
UPDATE oauth2_authorization
SET refresh_token_value = NULL,
    refresh_token_issued_at = NULL,
    refresh_token_expires_at = NULL,
    refresh_token_metadata = NULL
WHERE refresh_token_value IS NOT NULL
  AND refresh_token_expires_at IS NOT NULL
  AND refresh_token_expires_at < :cutoff;
~~~

Once a refresh token expires, clients can no longer refresh with it. The access token in the same authorization might still be valid; therefore, never delete the whole row solely because the refresh token expired.

### 4.4. Cleaning Up OIDC ID Tokens

Do not run a generic `UPDATE` conditioned solely on `oidc_id_token_expires_at`. The default authorization schema lacks a universal session-end column indicating whether RP-Initiated Logout may still use the ID Token hint. If you need to clear ID Tokens individually while other tokens remain, add application-managed retention/session eligibility state and clear them only after the UserInfo window, access-token dependency, and logout eligibility window have all closed.

An ID Token is distinct from an access token. Clients typically keep ID Tokens on their side for OIDC sessions; the Authorization Server does not need to keep ID Tokens indefinitely after expiry and retention windows. However, **never delete ID Tokens based solely on `exp`** if the OP still supports RP-Initiated Logout or UserInfo backed by that authorization. OIDC allows an OP to process an expired ID Token hint while the RP session is current/recent; Spring Authorization Server's default UserInfo mapper may also extract claims from the ID Token stored in the authorization. Retain ID Tokens until related access-token/UserInfo windows and session/logout eligibility windows have ended, then clean them up per retention policy.

### 4.5. Cleaning Up User Codes and Device Codes

~~~sql
UPDATE oauth2_authorization
SET user_code_value = NULL,
    user_code_issued_at = NULL,
    user_code_expires_at = NULL,
    user_code_metadata = NULL
WHERE user_code_value IS NOT NULL
  AND user_code_expires_at IS NOT NULL
  AND user_code_expires_at < :cutoff;
~~~

~~~sql
UPDATE oauth2_authorization
SET device_code_value = NULL,
    device_code_issued_at = NULL,
    device_code_expires_at = NULL,
    device_code_metadata = NULL
WHERE device_code_value IS NOT NULL
  AND device_code_expires_at IS NOT NULL
  AND device_code_expires_at < :cutoff;
~~~

These two token types relate to the Device Authorization Grant. When clearing them, still preserve access/refresh tokens if the authorization completed and those tokens remain valid.

### 4.6. Deleting Authorizations with No Remaining Tokens

After clearing expired tokens by type, delete authorizations that hold no remaining token values:

~~~sql
DELETE FROM oauth2_authorization
WHERE authorization_code_value IS NULL
  AND access_token_value IS NULL
  AND oidc_id_token_value IS NULL
  AND refresh_token_value IS NULL
  AND user_code_value IS NULL
  AND device_code_value IS NULL;
~~~

This statement is the final step of the per-token cleanup strategy. Use it only when every token type possible in the schema and custom extensions has been handled. If the application has extra token types, add matching conditions. Never delete rows containing token values without determined expiries.

If you prefer not to clear individual tokens, delete rows with a predicate checking every token:

~~~sql
DELETE FROM oauth2_authorization
WHERE (authorization_code_value IS NULL
       OR (authorization_code_expires_at IS NOT NULL
           AND authorization_code_expires_at < :cutoff))
  AND (access_token_value IS NULL
       OR (access_token_expires_at IS NOT NULL
           AND access_token_expires_at < :cutoff))
  AND oidc_id_token_value IS NULL
  AND (refresh_token_value IS NULL
       OR (refresh_token_expires_at IS NOT NULL
           AND refresh_token_expires_at < :cutoff))
  AND (user_code_value IS NULL
       OR (user_code_expires_at IS NOT NULL
           AND user_code_expires_at < :cutoff))
  AND (device_code_value IS NULL
       OR (device_code_expires_at IS NOT NULL
           AND device_code_expires_at < :cutoff));
~~~

This predicate ensures every present token value has been cleared per policy. Tokens with independent expiries are compared against `cutoff`; specifically, ID Tokens are cleared only once the application confirms no UserInfo or logout dependencies remain. One active token, an ID Token still inside its retention window, or a token lacking an expiry blocks deleting the entire row.

## 5. Batched Cleanup and Transactions

Never delete millions of authorizations in a single transaction. An oversized transaction holds row locks for too long, inflates WAL, causes replica lag, worsens bloat, and disrupts live token requests.

### 5.1. Using Batches with SKIP LOCKED

PostgreSQL supports `FOR UPDATE SKIP LOCKED`, allowing multiple workers to pick distinct rows without blocking one another. Example deleting authorizations where all tokens have expired:

~~~sql
WITH candidates AS (
    SELECT id
    FROM oauth2_authorization
    WHERE (authorization_code_value IS NULL
           OR (authorization_code_expires_at IS NOT NULL
               AND authorization_code_expires_at < :cutoff))
      AND (access_token_value IS NULL
           OR (access_token_expires_at IS NOT NULL
               AND access_token_expires_at < :cutoff))
      AND oidc_id_token_value IS NULL
      AND (refresh_token_value IS NULL
           OR (refresh_token_expires_at IS NOT NULL
               AND refresh_token_expires_at < :cutoff))
      AND (user_code_value IS NULL
           OR (user_code_expires_at IS NOT NULL
               AND user_code_expires_at < :cutoff))
      AND (device_code_value IS NULL
           OR (device_code_expires_at IS NOT NULL
               AND device_code_expires_at < :cutoff))
    ORDER BY id
    LIMIT :batch_size
    FOR UPDATE SKIP LOCKED
)
DELETE FROM oauth2_authorization authorization
USING candidates
WHERE authorization.id = candidates.id;
~~~

Each execution processes at most `batch_size` rows. Repeat in short transactions until deleted rows reach `0` or the maintenance window time limit expires.

`SKIP LOCKED` prevents multiple cleanup workers from locking on the same rows. It does not substitute for accurate expiry predicates and does not make deleting rows with active tokens safe.

### 5.2. Clearing Individual Tokens in Batches

The `UPDATE` statements in the previous section can be batched using an ID-selecting CTE:

~~~sql
WITH candidates AS (
    SELECT id
    FROM oauth2_authorization
    WHERE access_token_value IS NOT NULL
      AND access_token_expires_at IS NOT NULL
      AND access_token_expires_at < :cutoff
    ORDER BY id
    LIMIT :batch_size
    FOR UPDATE SKIP LOCKED
)
UPDATE oauth2_authorization authorization
SET access_token_value = NULL,
    access_token_issued_at = NULL,
    access_token_expires_at = NULL,
    access_token_metadata = NULL,
    access_token_type = NULL,
    access_token_scopes = NULL
FROM candidates
WHERE authorization.id = candidates.id;
~~~

Use the same pattern for authorization codes, refresh tokens, user codes, and device codes. For ID Tokens, apply a separate retention/session eligibility policy; never rely on `expires_at` alone because the token may still serve UserInfo or RP-Initiated Logout.

These SQL statements act directly on the table and bypass `OAuth2AuthorizationService` logic. If the application uses a cache or custom wrapper around the JDBC service, invalidate matching cache entries after cleanup. Run the SQL against the exact database/schema used by the Authorization Server; never mutate in-memory authorization objects while forgetting to persist the updated state.

### 5.3. Short Transactions and Retries

Each batch should be an independent transaction:

1. Compute `cutoff` once per run or pass a fixed `cutoff` to each batch.
2. Select and lock candidate rows.
3. Update/delete.
4. Commit.
5. Record metrics for processed row counts.
6. Proceed to the next batch if more rows remain.

If a transaction fails, roll back that batch and retry with bounded backoff. Never loop infinitely on schema errors, deadlocks, or permission errors. Log error codes and batch IDs, never token values.

### 5.4. Running Jobs Across Multiple Instances

If every Authorization Server instance runs the same scheduled cleanup:

- Use `SKIP LOCKED` to avoid processing duplicate rows across batches.
- Or use a distributed scheduler/leader election if only one instance should coordinate.
- Avoid one long transaction wrapping the entire loop.
- Configure timeouts, batch caps, and maintenance windows.
- Ensure the job never runs concurrently with schema migrations.

If cleanup runs concurrently with refreshes/revocations, row-level locking and transaction isolation serialize operations on the same authorization. Predicates must still re-verify expiry inside the transaction; never select IDs at one time and delete them later without rechecking conditions.

## 6. Implementing a Cleanup Job in Spring

Spring Authorization Server supplies JDBC persistence services, yet the application still owns retention and cleanup scheduling. Never assume using `JdbcOAuth2AuthorizationService` automatically provisions a production-ready retention job.

You can split responsibilities into two components:

- `AuthorizationCleanupScheduler`: coordinates scheduling and the batch loop.
- `AuthorizationCleanupRepository`: executes cleanup SQL statements via `NamedParameterJdbcTemplate`.

Scheduler structure example:

~~~java
@Component
@RequiredArgsConstructor
public class AuthorizationCleanupScheduler {

    private final AuthorizationCleanupService cleanupService;
    private final Clock clock;

    private final Duration gracePeriod = Duration.ofDays(7);
    private final int batchSize = 500;

    @Scheduled(cron = "0 30 2 * * *")
    public void cleanupExpiredAuthorizations() {
        Instant cutoff = clock.instant().minus(gracePeriod);

        int deleted;
        do {
            deleted = cleanupService.deleteExpiredBatch(cutoff, batchSize);
        } while (deleted == batchSize);
    }
}
~~~

Service executing one batch in its own transaction:

~~~java
@Service
@RequiredArgsConstructor
public class AuthorizationCleanupService {

    private final AuthorizationCleanupRepository repository;

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public int deleteExpiredBatch(Instant cutoff, int batchSize) {
        return repository.deleteExpiredBatch(cutoff, batchSize);
    }
}
~~~

This skeleton illustrates transaction boundaries; `AuthorizationCleanupRepository` must use SQL matching the deployed database and schema. Enable scheduling with `@EnableScheduling`, configure `Clock`, validate `batchSize > 0`, and bound total runtime per execution. When running multiple instances, add suitable distributed scheduling or batch locking.

Transactional methods must be invoked through a Spring proxy from another bean; self-invocation within the same bean may bypass the transaction interceptor. For long-running jobs, keep each batch in a short transaction and never wrap the entire loop in an outer transaction.

### 6.1. Avoid Running Cleanup Before the Schema Is Ready

Never run cleanup before schema migrations finish. During deployment:

1. Apply database migrations.
2. Verify the schema version.
3. Start the Authorization Server.
4. Verify JDBC services operate properly.
5. Only then allow scheduled cleanup to run.

Use a feature flag to pause cleanup during restores, migrations, or incident response. Never let an older instance run cleanup SQL against an incompatible newer schema.

## 7. Indexes, Query Plans, and Database Maintenance

Cleanup can degrade into a full table scan if the table is large and lacks appropriate indexes.

### 7.1. Evaluating Indexes Against Actual Queries

Columns commonly used in expiry predicates:

- `authorization_code_expires_at`;
- `access_token_expires_at`;
- `oidc_id_token_expires_at`;
- `refresh_token_expires_at`;
- `user_code_expires_at`;
- `device_code_expires_at`.

PostgreSQL can use partial indexes, e.g.:

~~~sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS
    idx_oauth2_authorization_access_expiry
ON oauth2_authorization (access_token_expires_at)
WHERE access_token_value IS NOT NULL;
~~~

Create such indexes only when query plans prove they help. In PostgreSQL, `CREATE INDEX CONCURRENTLY` cannot execute inside a transaction block; place this migration in a separate deployment step compatible with your migration tool. Multi-column predicates combining `AND`/`OR` can lead the optimizer to choose a bitmap scan or sequential scan; no single index set fits all workloads.

### 7.2. Inspecting Query Plans

Use `EXPLAIN` to check whether cleanup queries perform full table scans. When running `EXPLAIN ANALYZE`, remember that `UPDATE`/`DELETE` statements actually execute; test in staging or inside a controlled rolled-back transaction.

Monitor:

- rows scanned vs. rows deleted;
- batch duration;
- lock waits and deadlocks;
- WAL generation;
- replication lag;
- table/index sizes and dead tuples.

### 7.3. VACUUM and Bloat

PostgreSQL does not automatically shrink database files immediately after `DELETE`. Dead tuples are reclaimed by `VACUUM`; disk space is usually reused within the table rather than returned immediately to the filesystem. Monitor autovacuum and table bloat, and avoid running `VACUUM FULL` casually in production because it takes strong locks and rewrites the table.

Steady batched cleanup is usually far better than a massive monthly delete.

## 8. Retention for Consents, Clients, and Audits

### 8.1. Authorization Consents

`oauth2_authorization_consent` stores granted consents between principals and registered clients. This table has no access/refresh token expiry. Consent deletion policies should be driven by:

- user requests to revoke consent;
- decommissioned or unused clients;
- privacy/data retention requirements;
- closed tenants/accounts;
- organizational regulatory retention limits.

Never delete consents merely because an authorization token expired. Consents can be reused on future authorizations; deleting them forces users to consent again.

### 8.2. Registered Clients

`oauth2_registered_client` holds client configurations and credentials. Deleting registrations requires its own lifecycle workflow:

1. Stop issuing new tokens to the client.
2. Revoke or wait for existing authorizations/tokens to expire.
3. Handle refresh tokens and consents per policy.
4. Keep audit/tombstone records long enough for investigations and to prevent client ID reuse.
5. Delete the registration only when no authorizations need it and the retention window has elapsed.

Never delete a client solely because `client_name` looks old or the client was idle for a few days.

### 8.3. Audits and Security History

Audit records normally have a retention policy separate from token data. You may need to keep client creation events, redirect URI changes, token revocations, consent withdrawals, and administrative actions longer than authorization rows.

Never store raw access tokens, refresh tokens, client secrets, or private keys in audit logs. If an event must reference a token, use a suitable token identifier/hash and restrict access.

## 9. What Must Backups Include?

A backup capable of restoring an Authorization Server must include every component needed for the server to continue authenticating clients, reading authorizations, and signing/verifying tokens.

| Component | Reason to back up |
| --- | --- |
| `oauth2_registered_client` | Restores client IDs, encoded credentials, redirect URIs, grant types, scopes, and settings. |
| `oauth2_authorization` | Restores authorizations, access/refresh tokens, ID Tokens, and revocation/invalidated metadata state. |
| `oauth2_authorization_consent` | Restores consents for a consistent authorization experience. |
| Signing keys/JWK material or KMS/HSM references | Signs new tokens and preserves ability to verify existing tokens. |
| Issuer and endpoint configuration | Keeps `iss`, endpoint URLs, key selection, and client discovery consistent. |
| Database schema/migration version | Ensures row mappers and SQL match stored data. |
| Encryption keys/secret references | Decrypts data or accesses secret stores after restore. |
| External session stores and security state | Restores or proactively invalidates OP sessions as needed. |
| Audit and administrative records | Investigates changes, revocations, and admin operations. |

### 9.1. Database Backups Do Not Automatically Include Signing Keys

`JWKSource` may load keys from a database, filesystem, secret manager, KMS, or HSM. Never assume private signing keys live inside the three JDBC tables.

When keys reside outside the database:

- back up keys per your KMS/HSM or secret manager procedures;
- record key IDs/versions and access permissions;
- ensure the restored application can access required keys;
- retain old public keys long enough for Resource Servers to verify already-issued tokens;
- never export private keys into plain backup files if the platform offers safer backup mechanisms.

A database snapshot cannot restore token-signing capability if the private key was lost or KMS access is gone.

### 9.2. Backups Are Sensitive Data

`oauth2_authorization` may contain bearer token values, claims, and PII. Backups require:

- encryption in transit and at rest;
- least-privilege access and auditing on every restore;
- storing backups in isolated accounts/storage;
- immutable retention or object locks to defend against ransomware;
- managing encryption keys separately from backups;
- retention policies to purge expired backups;
- strict controls over copying production data into staging/development.

Never send backups or database dumps over email/chat, and never write token values into logs.

## 10. PostgreSQL Backups and Point-in-Time Recovery

Backup strategies should combine logical backups, physical/base backups, and WAL archiving according to RPO/RTO.

### 10.1. Logical Backups with pg_dump

Example creating a custom-format backup:

~~~bash
pg_dump \
  --format=custom \
  --no-owner \
  --file=authorization-server.dump \
  --dbname=authorization_server
~~~

List objects inside the archive:

~~~bash
pg_restore --list authorization-server.dump
~~~

Logical backups suit migrations, data inspection, restoring a single database, or moving environments. They capture a consistent snapshot at dump time, but do not replace WAL archiving when you must recover to an arbitrary point in time after a base backup.

Use `.pgpass`, service files, or a secret manager to supply credentials; avoid putting passwords directly on command lines or in scripts committed to repositories.

`pg_dump` backs up only a single database; global objects like database roles and tablespaces must be managed/backed up separately per organizational PostgreSQL procedures (e.g., `pg_dumpall --globals-only`). Ensure roles and grants are restored properly before the application connects.

### 10.2. Physical Backups and WAL Archiving

For low-RPO requirements, PostgreSQL can combine base backups with WAL archiving to support PITR:

- take periodic base backups;
- enable WAL archiving and ship WAL segments continuously to independent storage;
- monitor archive failures and WAL gaps;
- retain base backups/WAL per retention policy;
- periodically run restore drills to a chosen timestamp.

PITR requires both a complete base backup and a continuous WAL chain. Having WAL files without a matching base backup is not enough to recover.

### 10.3. Backup Consistency

`oauth2_registered_client`, `oauth2_authorization`, and `oauth2_authorization_consent` should be backed up within one consistent database snapshot. If they reside in separate databases, design snapshot/coordination procedures to avoid client-authorization state skew.

Issuer configurations, key IDs, key material, and external session stores need checkpoints/versions compatible with the snapshot. Record the timestamp and schema migration version of each backup.

## 11. Restoring into an Isolated Environment

Never overwrite production during a first rehearsal. Restore into an isolated database and environment to verify first.

### 11.1. Restoring a Logical Backup into a New Database

~~~bash
createdb authorization_server_restore

pg_restore \
  --exit-on-error \
  --no-owner \
  --dbname=authorization_server_restore \
  authorization-server.dump
~~~

After restoring:

1. Check ownership, grants, and database extensions.
2. Verify schema/migration version.
3. Point the application configuration at the restored database.
4. Connect environment-appropriate signing keys/KMS.
5. Check the issuer and public JWKS.
6. Run smoke tests with a test client.
7. Consider cutover only after verification.

Never run `--clean` or overwrite a production database without a change plan, a pre-operation snapshot, and a rollback plan.

### 11.2. Checking Row Counts and Consistency

Cross-check queries:

~~~sql
SELECT COUNT(*) AS registered_clients
FROM oauth2_registered_client;

SELECT COUNT(*) AS authorizations
FROM oauth2_authorization;

SELECT COUNT(*) AS consents
FROM oauth2_authorization_consent;

SELECT COUNT(*) AS authorizations_with_active_access_token
FROM oauth2_authorization
WHERE access_token_value IS NOT NULL
  AND access_token_expires_at > CURRENT_TIMESTAMP;
~~~

Row counts only detect missing tables or anomalous data drops. They do not prove tokens can be verified, clients can log in, or refresh flows work.

### 11.3. Post-Restore Smoke Tests

Execute checks through application services/APIs:

- `RegisteredClientRepository.findByClientId(...)` locates expected clients.
- `OAuth2AuthorizationService.findById(...)` reads test authorizations.
- `OAuth2AuthorizationService.findByToken(...)` locates unexpired test tokens by token type.
- Unexpired tokens verify against appropriate current/previous keys.
- Unexpired refresh tokens complete refresh flows in the test environment.
- Revoked/invalidated tokens remain rejected.
- Consents read back accurately.
- Discovery metadata publishes the right issuer and JWKS URI.

Never use real production tokens in staging smoke tests when dedicated test clients and authorizations can be created.

## 12. Special Risk When Restoring an Old Backup: Revocations Can Be Rolled Back

This is a critical security risk that requires dedicated mitigation.

Suppose:

1. At 10:00, the database records refresh token R1 as valid.
2. At 11:00, the user revokes R1; the database records invalidated status.
3. At 12:00, the system restores a snapshot taken at 10:30.

After the restore, the database no longer knows R1 was revoked. If authorization/token state is read directly from the database, the old state makes the token appear unrevoked.

~~~mermaid
sequenceDiagram
    participant DB as Authorization DB
    participant AS as Authorization Server
    participant RS as Resource Server

    AS->>DB: 10:00: Save active refresh token R1
    AS->>DB: 11:00: Mark R1 revoked
    Note over DB: Backup snapshot at 10:30
    AS->>DB: 12:00: Restore 10:30 snapshot
    AS->>DB: Read R1 authorization
    DB-->>AS: Pre-revocation state
    AS->>AS: Must apply recovery security policy
    AS-->>RS: Resume serving only after handling token state
~~~

Impact depends on token format and Resource Server behavior:

- Opaque tokens/introspection may become active again if pre-revocation state is restored.
- Offline-verified JWTs do not directly rely on the current revocation row anyway; database restores do not automatically expire JWTs.
- Refresh tokens may be accepted again if invalidation state was rolled back.
- Client registrations or secret rotations newer than the snapshot may also be lost.

### 12.1. Recovery Controls

After restoring from a snapshot older than critical security changes:

- pause token issuance/refreshing during assessment;
- compare the snapshot timestamp against revocation, credential rotation, and incident logs;
- revoke or rotate credentials that may have been rolled back;
- invalidate sessions per policy;
- enforce a denylist/epoch/monotonic security state in an independent store if the system must guarantee tokens cannot resurrect;
- require re-authentication or re-consent where needed;
- reopen traffic only after verifying token state and keys.

When security requirements are strict, record revocations/security events in an append-only or independently replicated store separate from rollback-prone database snapshots. A technically successful database restore is not automatically a safe state to serve traffic.

## 13. Disaster Recovery: RPO, RTO, and Runbooks

Set targets before an incident occurs:

| Metric | Meaning | Example decisions |
| --- | --- | --- |
| RPO (Recovery Point Objective) | Maximum acceptable data loss. | At most 5 minutes of authorization/revocation updates or 1 hour? |
| RTO (Recovery Time Objective) | Maximum time to restore service. | Restore issuer within 30 minutes or 4 hours? |
| Backup retention | How long backups are kept. | Daily snapshots, weekly/monthly archives, and legal retention. |
| PITR window | Time range recoverable via point-in-time recovery. | 7, 14, or 35 days based on WAL retention and cost. |
| Key recovery objective | Time to restore signing/verification keys. | KMS/HSM failover and emergency access procedures. |

### 13.1. Recovery Runbook

A practical runbook:

1. Confirm the incident, scope of data corruption, and last known consistent database timestamp.
2. Block or throttle traffic to the Authorization Server if continuing to issue tokens poses risk.
3. Select the base backup/snapshot and PITR target.
4. Restore into an isolated database.
5. Restore key access, issuer config, secret references, and session dependencies.
6. Verify schemas, row counts, client registrations, authorizations, and consents.
7. Assess revocations, client secret rotations, and security events occurring after the snapshot timestamp.
8. Run smoke/integration tests.
9. Decide on required invalidations/rotations before cutover.
10. Switch traffic, monitoring token/refresh/login errors and replication.
11. Record actual recovery time, data loss, and follow-up improvements.

### 13.2. Restore Drills

A backup is only trustworthy once successfully restored. Schedule drills:

- restore a recent backup into staging;
- restore to a chosen PITR timestamp;
- verify signing keys/JWKS and token validation;
- verify client credentials and consents;
- run refresh/revocation tests;
- measure actual elapsed time against RTO;
- verify backup encryption keys and access permissions;
- document failures and update the runbook.

Never wait until the production database fails to test `pg_restore` or emergency KMS access.

## 14. Common Operational Mistakes

### 14.1. Deleting Authorizations Based on access_token_expires_at

A row may still hold a valid refresh token. Delete the entire row only once all tokens have expired or been cleared per policy.

### 14.2. Clearing Refresh Tokens While Forgetting Metadata

Token value, issued-at, expires-at, and metadata columns must be handled synchronously. Inspect the row mapper schema before writing custom SQL.

### 14.3. Cleanup Running Too Long and Locking Token Requests

Reduce batch sizes, use short transactions, index according to actual queries, cap batches per run, and monitor lock waits/replication lag.

### 14.4. Deleting Consents Alongside Tokens

Consents do not share expiration with authorizations. Manage consents under a dedicated retention policy.

### 14.5. Restoring the Database Without Signing Keys

The Authorization Server may start yet fail to sign tokens, or Resource Servers may fail to validate older tokens. Verify JWK/KMS/HSM before cutover.

### 14.6. Restoring a Snapshot Loses Newer Revocations

This is a security state rollback. Cross-check snapshots against independent security events and handle tokens/sessions/credentials before reopening traffic.

### 14.7. Using Production Backups Directly in Staging

Backups contain tokens, claims, client data, and PII. Isolate environments, restrict egress, protect keys, and sanitize data if the goal is solely testing.

### 14.8. Using SQL Schemas from the Wrong Version

Migrations may add or alter columns. Cleanup SQL must match the running schema; verify migrations and test in staging before production.

### 14.9. Large Tables Lacking Expiry Indexes

Cleanup scans the whole table, generating heavy I/O and impacting workloads. Measure query plans before adding indexes; consider partial indexes scoped to present token values.

### 14.10. Running Cleanup Simultaneously with Migrations or Restores

The job could write against an unready schema or delete data during restore validation. Use a maintenance flag and re-enable only after verification.

## 15. Cleanup, Backup, and Restore Test Matrix

| Scenario | Expected outcome |
| --- | --- |
| Authorization with only a code expired past cutoff | Eligible for cleanup per policy. |
| Expired code with unexpired access token | Row retained; if clearing per token, only code fields are nulled. |
| Expired access token with unexpired refresh token | Refresh token and authorization preserved. |
| Expired refresh token with unexpired access token | Access token preserved; only refresh fields cleared. |
| Expired ID Token with unexpired access token | Do not delete access token; retain ID Token if UserInfo or logout still needs it. |
| Expired ID Token while OP session remains within logout eligibility window | Keep ID Token hint until logout and UserInfo windows end. |
| ID Token past UserInfo/logout retention window and flagged eligible by policy | Clear only ID Token per dedicated policy; other valid tokens unaffected. |
| Expired device/user code with unexpired access token | Clear only device/user code fields. |
| Token value present with `NULL` expiry | Do not automatically clear token or row. |
| All token values `NULL` after cleanup | Row eligible for deletion per retention policy. |
| Small batch size | Each transaction processes at most batch size rows. |
| Two cleanup workers running concurrently | No duplicate deletes or prolonged lock waits; `SKIP LOCKED` works as designed. |
| Refresh request concurrent with cleanup | Authorization with active tokens is not deleted. |
| Long-lived consent still required | Never deleted by token cleanup. |
| Client with active authorizations | Registered client is not deleted. |
| Backup during token issuance | Consistent snapshot per database guarantees. |
| Restore logical backup into a new database | Tables and rows are recovered. |
| PITR restore | Data matches chosen timestamp and continuous WAL. |
| Restore missing signing keys | Smoke test catches it prior to cutover. |
| Restore snapshot older than a revocation | Recovery procedure detects and mitigates rollback. |
| Restore into staging | Secrets/keys isolated; sensitive data controlled. |
| Cleanup SQL after schema migration | SQL stays compatible with actual schema. |
| Inaccessible backup encryption key | Restore drill fails and gets logged before a real incident. |
| Timed restore test | Meets defined RTO target. |

### 15.1. Integration Tests with Mixed Token Data

Create several authorization fixtures:

- A: expired authorization code, valid access token, valid refresh token.
- B: expired access token, valid refresh token.
- C: expired refresh token, valid access token.
- D: all tokens expired past grace period.
- E: token value with `NULL` expiry.
- F: expired device/user code, valid access token.

Run cleanup inside a test transaction and verify:

1. A, B, C, E, and F still retain their authorization rows.
2. Expired token fields are cleared according to strategy.
3. Valid tokens are still found by `OAuth2AuthorizationService.findByToken(...)`.
4. D is deleted once all token conditions are satisfied.
5. Consents and registered clients are untouched outside policy.

### 15.2. Backup/Restore Integration Drill

- Create test registered clients, consents, and authorizations.
- Back up the database.
- Modify a registration, revoke a token, and create a new authorization.
- Restore the backup into an isolated database.
- Verify data matches the snapshot and identify post-snapshot changes that were lost.
- Verify signing keys, issuer, and token validation.
- Execute recovery controls so tokens revoked after the snapshot are not mistakenly revived.
- Record restore duration and results against RPO/RTO.

## 16. Deployment Checklist

- [ ] Cleanup SQL matches the JDBC schema for the exact Spring Authorization Server version.
- [ ] Understood that one authorization row can contain multiple token types.
- [ ] Cleanup predicates inspect each token expiry rather than relying on a single column.
- [ ] Token values with `NULL` expiry are retained until an explicit policy applies.
- [ ] Grace period and shared UTC timekeeping are configured.
- [ ] Strategy exists for clearing individual tokens or deleting rows once all tokens expire.
- [ ] Token fields and metadata are cleared synchronously.
- [ ] Authorizations with active refresh/access/device tokens are never deleted.
- [ ] Batch size, transaction timeout, and retries are bounded.
- [ ] Multi-instance jobs use `SKIP LOCKED`, scheduler locks, or proper leader election.
- [ ] Consents and registered clients have independent retention policies.
- [ ] Audits never store raw tokens, secrets, or private keys.
- [ ] Query plans and expiry indexes measured before deployment.
- [ ] Monitoring covers WAL, replica lag, lock waits, dead tuples, and cleanup metrics.
- [ ] Consistent backup snapshots cover critical JDBC tables.
- [ ] WAL archiving/PITR configured if low RPO is required.
- [ ] Backups include or reference signing keys, KMS/HSM, and issuer configuration.
- [ ] Backups are encrypted, least-privilege restricted, and stored separately.
- [ ] Schema versions, migration state, and restore runbooks are documented.
- [ ] Restore drills run periodically and are measured against RTO.
- [ ] Procedures exist to handle revocations/credential rotations rolled back by old restores.
- [ ] Production backups are never opened directly in unisolated staging environments.
- [ ] Cleanup is paused during migrations, restores, and incident response.
- [ ] Integration tests cover mixed tokens, concurrency, backups, and restores.

**Key Takeaway:** Treat `oauth2_authorization` as an aggregate holding multiple tokens with independent expiries. Clear individual tokens or delete the whole row only when all tokens have expired past the retention cutoff. Backups must preserve consistency across clients, authorizations, consents, and signing keys. After restoring an older snapshot, always check for revocation rollbacks before reopening traffic.

## 17. References

- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `JdbcOAuth2AuthorizationService`, `JdbcOAuth2AuthorizationConsentService`, `JdbcRegisteredClientRepository`, and persistence components.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): configuring the Authorization Server and required services.
- [Spring Authorization Server — How-to: Implement core services with JPA](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-jpa.html): reference persistence models and service boundaries when customizing storage.
- [Spring Authorization Server — Source repository](https://github.com/spring-projects/spring-authorization-server): official SQL schemas bundled with your exact dependency version.
- [PostgreSQL — pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html): consistent logical backups.
- [PostgreSQL — pg_restore](https://www.postgresql.org/docs/current/app-pgrestore.html): restoring archives.
- [PostgreSQL — Continuous Archiving and Point-in-Time Recovery](https://www.postgresql.org/docs/current/continuous-archiving.html): base backups, WAL archiving, and PITR.
- [PostgreSQL — SELECT locking clause](https://www.postgresql.org/docs/current/sql-select.html): `FOR UPDATE SKIP LOCKED`.
- [PostgreSQL — VACUUM](https://www.postgresql.org/docs/current/sql-vacuum.html): reclaiming and reusing space after `DELETE`/`UPDATE`.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009.html): token revocation semantics and effects on related tokens.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): refresh token protection, rotation, and current OAuth security practices.
