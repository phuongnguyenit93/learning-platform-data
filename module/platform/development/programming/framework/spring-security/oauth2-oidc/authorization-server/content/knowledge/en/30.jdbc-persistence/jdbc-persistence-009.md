# Indexes, Token Lookups, and the Impact of Data Size

## 1. Context and Objectives

In an **OAuth 2.0/OpenID Connect Authorization Server** built with **Spring Security**, **Spring Authorization Server**, and **Spring Boot**, many token issuance, verification, introspection, and revocation flows must locate a persisted authorization record. As clients, users, and tokens grow, query costs on the authorization table can become a significant share of Token Endpoint, Introspection Endpoint, or Revocation Endpoint latency.

An Authorization Server can store multiple types of values inside a single record: authorization code, access token, refresh token, ID Token, user code, device code, and state. Each type has its own lifetime, metadata, and lookup frequency. The record also holds the principal, `RegisteredClient` ID, scopes, attributes, claims, and serialized metadata. Therefore, performance depends on both **how quickly the right row is located** and **how much data must be read/written once the row is found**.

Running example: a system at `identity.example.com` issues access tokens to hundreds of internal applications. Resource Servers call introspection frequently; some clients use opaque tokens and some use JWTs. When revoking a refresh token, the Authorization Server must find the authorization containing that token, mark the token invalidated, and save it back. Initially the table holds a few thousand rows; a year later it has tens of millions. If every token lookup triggers a table scan or reads large LOBs, latency and I/O climb rapidly.

After this lesson, you will be able to:

1. Understand the `oauth2_authorization` table structure and the columns used for token lookups.
2. Explain how `JdbcOAuth2AuthorizationService.findByToken(token, tokenType)` builds SQL conditions.
3. Distinguish lookups with a specific token type from lookups with an unknown token type.
4. Design indexes suited to the database's data types and workload.
5. Understand why BLOB/CLOB columns or very long tokens make direct indexing difficult.
6. Design a token lookup table using HMAC digests when direct indexing on token values is unsuitable.
7. Assess the impact of attributes, claims, metadata, and token count on row size.
8. Optimize consent queries, client/principal queries, and expired-authorization cleanup jobs.
9. Read execution plans, measure latency, and benchmark before/after adding indexes.
10. Recognize when `JdbcOAuth2AuthorizationService` should be replaced by a specialized implementation.

**Version Scope:** Content references Spring Authorization Server **1.5.8** and Spring Security 6.x. Table/column names and schemas must be cross-checked against the exact SQL resource bundled with your running dependency. SQL examples use PostgreSQL when explicitly specifying `bytea`/`timestamptz`; other database engines require adapting data types and syntax.

## 2. Authorization Data Model

### 2.1. OAuth2Authorization Holds Multiple Tokens and Metadata

`OAuth2Authorization` is not merely a single row holding an access token. The domain object comprises these main parts:

| Component | Meaning | Example |
| --- | --- | --- |
| `id` | Unique ID of the authorization. | `auth-7f32...` |
| `registeredClientId` | Internal ID of the `RegisteredClient`. | `client-record-001` |
| `principalName` | Principal of the resource owner or client. | `alice` or `batch-worker` |
| `authorizationGrantType` | Grant type that created the authorization. | `authorization_code`, `client_credentials` |
| `authorizedScopes` | Approved scopes. | `openid`, `profile`, `orders.read` |
| `attributes` | Flow-specific additional data. | Principal, authorization request, nonce, state, and other data |
| `tokens` | Issued tokens and matching metadata. | Authorization Code, Access Token, Refresh Token, ID Token, Device Code |

One authorization can accumulate multiple tokens over its lifecycle. For instance, the Authorization Code Flow initially persists the authorization code, then updates to store the access token, refresh token, and ID Token. During refresh, the same record may be updated with new tokens or invalidation metadata.

### 2.2. The oauth2_authorization Table

`JdbcOAuth2AuthorizationService` depends on the `oauth2-authorization-schema.sql` schema resource. The default DDL uses a **flattened** structure: tokens and metadata are spread across many columns in one table rather than split into a separate token table.

Key columns:

| Group | Typical columns | Purpose |
| --- | --- | --- |
| Keys and subjects | `id`, `registered_client_id`, `principal_name` | Identifies authorization, client, and principal. |
| Flow | `authorization_grant_type`, `authorized_scopes` | Grant type and scopes. |
| Attributes | `attributes` | Additional JSON/serialized data. |
| State | `state` | OAuth state used in authorization flows. |
| Authorization Code | `authorization_code_value`, `authorization_code_issued_at`, `authorization_code_expires_at`, `authorization_code_metadata` | Code lookup and code state. |
| Access Token | `access_token_value`, `access_token_issued_at`, `access_token_expires_at`, `access_token_metadata`, `access_token_type`, `access_token_scopes` | Access token lookup, token type, scopes, and metadata. |
| Refresh Token | `refresh_token_value`, `refresh_token_issued_at`, `refresh_token_expires_at`, `refresh_token_metadata` | Refresh token lookup and management. |
| OIDC ID Token | `oidc_id_token_value`, `oidc_id_token_issued_at`, `oidc_id_token_expires_at`, `oidc_id_token_metadata` | Stores ID Token and metadata/claims. |
| Device Authorization | `user_code_value`, `device_code_value` plus issued/expires/metadata | User code and device code lookups. |

The schema bundled with Spring Authorization Server uses `BLOB` for several token value and metadata columns; for example, PostgreSQL requires replacing `BLOB` with an appropriate text type per schema notes. Actual column types depend on the database and your application's migrations.

The default DDL creates a primary key on `id`. Secondary indexes for token lookups are not pre-declared in the default authorization schema. Therefore, the application may need to design indexes tailored to its database and real workload.

### 2.3. The Consent Table

`oauth2_authorization_consent` stores permissions a user approved for a client:

~~~sql
CREATE TABLE oauth2_authorization_consent (
    registered_client_id varchar(100) NOT NULL,
    principal_name varchar(200) NOT NULL,
    authorities varchar(1000) NOT NULL,
    PRIMARY KEY (registered_client_id, principal_name)
);
~~~

The composite primary key `(registered_client_id, principal_name)` supports looking up consents by exact client and user pair. Because column order in a composite index matters, this index also serves queries filtering solely by `registered_client_id` in the leading position; it is not equally optimal for queries filtering solely by `principal_name`.

## 3. How JdbcOAuth2AuthorizationService Queries by Token

### 3.1. findById

`findById(id)` uses the predicate:

~~~sql
SELECT ...
FROM oauth2_authorization
WHERE id = ?;
~~~

This query uses the primary key, so it typically has an efficient access path. The default implementation's `save(authorization)` checks whether the authorization already exists via `findById` before inserting or updating. Thus, the write path may include a PK read followed by an INSERT/UPDATE.

### 3.2. findByToken with a Known Token Type

API:

~~~java
OAuth2Authorization findByToken(
    String token,
    OAuth2TokenType tokenType
);
~~~

When the caller knows the token type, the implementation selects a specific filter:

| Token type | Column compared |
| --- | --- |
| `state` | `state` |
| `code` | `authorization_code_value` |
| Access Token | `access_token_value` |
| ID Token | `oidc_id_token_value` |
| Refresh Token | `refresh_token_value` |
| User Code | `user_code_value` |
| Device Code | `device_code_value` |

Logical example of an access token query:

~~~sql
SELECT <authorization-columns>
FROM oauth2_authorization
WHERE access_token_value = ?;
~~~

This query has a single equality predicate on one column. If the database has an appropriate index and the data type allows full-value equality indexing, the optimizer can locate the row without scanning the entire table.

### 3.3. findByToken with Null tokenType

When `tokenType` is `null`, the service must search for the token value across every type supported by the implementation. Equivalent condition:

~~~sql
SELECT <authorization-columns>
FROM oauth2_authorization
WHERE state = ?
   OR authorization_code_value = ?
   OR access_token_value = ?
   OR oidc_id_token_value = ?
   OR refresh_token_value = ?
   OR user_code_value = ?
   OR device_code_value = ?;
~~~

This is an important performance distinction. The database may:

- Combine multiple indexes via bitmap/index-merge if columns are suitably indexed.
- Pick a suboptimal access path if statistics are stale.
- Perform a full table scan if no useful indexes exist or column types cannot be indexed.

Do not assume `OR` always causes a full scan; query planners depend on the database, cardinality, statistics, and column types. Nonetheless, an untyped token query has more branches and is generally harder to optimize than a single-column equality predicate.

### 3.4. When Might the Token Type Be Unknown?

Some protocol endpoints receive a token from a request without knowing yet which token type it is. `findByToken(token, null)` provides search semantics across all supported types. If a custom implementation changes how lookups work, it must preserve those exact semantics; never search only access tokens and miss refresh tokens, authorization codes, user codes, or device codes.

When the caller knows the token type from protocol context, passing the exact type lets the service use a targeted filter. Do not guess types from token string shapes or prefixes not guaranteed by the protocol.

### 3.5. SELECT Fetches the Entire Authorization Row

`JdbcOAuth2AuthorizationService` does not select only the ID when looking up a token. It loads the authorization columns and uses `RowMapper` to reconstruct `OAuth2Authorization`, including token values, metadata, attributes, and related fields.

Therefore, an index speeds up locating the right row, but does not eliminate the cost of:

- Reading LOB/BLOB/CLOB columns.
- Converting bytes/text.
- Deserializing JSON metadata and attributes.
- Constructing token objects and claims.
- Looking up the associated `RegisteredClient`.

When an authorization row holds multiple tokens and large metadata, read/mapping overhead can remain substantial even when the index lookup itself is fast.

## 4. Why the Default Schema Is Not Enough for High Throughput

### 4.1. Minimal Schema Prioritizes Compatibility

The default schema must work across many relational engines and support diverse grant types. Consequently, it provides a flattened layout with a PK on authorization ID and multiple token/metadata columns, but cannot be pre-tuned for every workload.

`JdbcOAuth2AuthorizationService` Javadoc describes it as a simplified JDBC implementation. It is usable in production, though it may fall short in high-throughput environments; applications are expected to provide a custom `OAuth2AuthorizationService` implementation if deployment performance demands it.

### 4.2. Indexes Must Match Actual Predicates

An index only helps if an SQL query uses a predicate supported by that index. For example:

- An index on `access_token_value` helps `WHERE access_token_value = ?`.
- An index on `refresh_token_value` does not optimize `WHERE access_token_value = ?`.
- A composite index `(registered_client_id, principal_name)` does not replace an index on token values.
- An index on `access_token_expires_at` helps expiry cleanup queries, not `findByToken`.

Before creating indexes, list actual queries and their call frequencies.

### 4.3. Indexes Increase Write Costs

Every secondary index must be updated on INSERT, UPDATE, or DELETE. `save(authorization)` may update multiple columns in a row; adding many indexes increases:

- Number of index/data pages written.
- WAL/redo logs and replication traffic.
- Storage footprint.
- Vacuum/maintenance overhead depending on the database.
- Fragmentation risk and buffer cache pressure.

Never create indexes on every column simply because it might appear in a rare query. An index's read benefit must outweigh its write and operational costs.

## 5. Designing Indexes for Token Lookups

### 5.1. When Token Columns Are Directly Indexable VARCHARs

If a custom schema uses bounded string types and the database supports full-value equality indexes on them, consider:

~~~sql
CREATE INDEX idx_oauth2_auth_access_token
    ON oauth2_authorization (access_token_value);

CREATE INDEX idx_oauth2_auth_refresh_token
    ON oauth2_authorization (refresh_token_value);

CREATE INDEX idx_oauth2_auth_code
    ON oauth2_authorization (authorization_code_value);

CREATE INDEX idx_oauth2_auth_id_token
    ON oauth2_authorization (oidc_id_token_value);

CREATE INDEX idx_oauth2_auth_user_code
    ON oauth2_authorization (user_code_value);

CREATE INDEX idx_oauth2_auth_device_code
    ON oauth2_authorization (device_code_value);
~~~

This example assumes a schema with indexable columns, not a migration applicable verbatim to the default DDL using `BLOB`. Verify index key length limits, encoding, collation, row size, and data type indexability on your database.

### 5.2. Why You Should Not Directly Index BLOB/CLOB Columns

BLOB/CLOB types are designed for large data. Many databases do not support standard B-tree indexes over entire LOBs; some allow only function-based indexes, prefix indexes, or indexes under strict size caps. Prefix indexes cannot guarantee exact equality if multiple tokens share the same prefix.

Even when a database allows indexing long `VARCHAR`s, indexing full JWTs/tokens can:

- Produce huge indexes.
- Hit index entry size limits.
- Increase INSERT/UPDATE overhead.
- Consume buffer cache.
- Store raw bearer tokens inside index pages, backups, and snapshots.

Thus, direct indexing on token values only works when column types, token lengths, and database behavior are verified. For long tokens or LOBs, consider a fixed-size lookup key.

### 5.3. Never Treat a Prefix Index as an Exact Index

Suppose a database supports prefix indexing:

~~~sql
-- Illustrative concept; syntax depends on the database.
CREATE INDEX idx_access_token_prefix
    ON oauth2_authorization (access_token_value(128));
~~~

A prefix index can narrow candidates, yet multiple tokens can share a prefix. The database still must inspect the remainder; the optimizer might skip the index if selectivity is low or predicates do not align. Never truncate tokens during comparison, never use prefixes as token identifiers, and never omit verifying the entire token value.

### 5.4. Fixed-Size Hash Digests

A common pattern is computing a digest of the token and indexing the digest rather than the full string. A SHA-256 digest is fixed at 32 bytes; HMAC-SHA-256 is also 32 bytes.

If you merely add a `token_hash` column alongside the token value, remember that **the default `JdbcOAuth2AuthorizationService` still queries the token value column**. Adding a hash column or hash index does not automatically switch default SQL statements to query the digest.

To use a hash index, you must:

1. Modify the mapper/write path to compute the digest when saving tokens.
2. Maintain digests across authorization updates, rotations, and removals.
3. Modify `findByToken` to hash the presented token.
4. Query by digest to obtain the authorization ID.
5. Load the corresponding authorization and preserve `OAuth2AuthorizationService` semantics.
6. Keep hash data synchronized with token values inside the same transaction.

### 5.5. Use HMAC Instead of Plain Hash for Low-Entropy Tokens

Authorization codes, access tokens, and refresh tokens typically have high entropy, but user codes/device codes or certain short identifiers may have smaller value spaces. Storing plain SHA-256 of short values lets anyone with a database copy attempt offline brute forcing.

For lookup indexes, consider HMAC-SHA-256 using a secret key managed by the application outside the database:

~~~java
byte[] tokenDigest(
        SecretKey lookupKey,
        String tokenType,
        String token) throws GeneralSecurityException {

    Mac mac = Mac.getInstance("HmacSHA256");
    mac.init(lookupKey);
    mac.update(tokenType.getBytes(StandardCharsets.UTF_8));
    mac.update((byte) 0);
    return mac.doFinal(token.getBytes(StandardCharsets.UTF_8));
}
~~~

Including `tokenType` in the input creates domain separation: the same token string under two different types yields distinct digests. Keep the secret key in a KMS/secret manager, never inside the database or logs.

HMAC lookup does not replace validating token protocol rules, expiry, invalidation, or client binding. It merely locates the row via an indexable value.

### 5.6. Token Lookup Side Table

When fast lookups across multiple token types are needed, extract the token → authorization ID mapping into its own table. PostgreSQL example:

~~~sql
CREATE TABLE oauth2_authorization_token_lookup (
    token_type varchar(32) NOT NULL,
    token_hash bytea NOT NULL,
    authorization_id varchar(100) NOT NULL,
    expires_at timestamptz,
    PRIMARY KEY (token_type, token_hash),
    FOREIGN KEY (authorization_id)
        REFERENCES oauth2_authorization(id)
        ON DELETE CASCADE
);

CREATE INDEX idx_oauth2_token_lookup_authorization
    ON oauth2_authorization_token_lookup (authorization_id);

CREATE INDEX idx_oauth2_token_lookup_expiry
    ON oauth2_authorization_token_lookup (expires_at);
~~~

The lookup table stores a fixed digest, token type, and authorization ID. Primary key `(token_type, token_hash)` serves equality lookups. Index `authorization_id` helps locate/delete mappings when an authorization is removed. The expiry index is only needed if a time-based cleanup job queries it; omit it if no query uses it.

`token_type` values should use a stable code set, such as `access_token`, `refresh_token`, `authorization_code`, `oidc_id_token`, `user_code`, `device_code`, `state`.

Lookup flow:

~~~mermaid
sequenceDiagram
    autonumber
    participant E as Introspection / Revocation
    participant S as Custom OAuth2AuthorizationService
    participant L as Token Lookup Table
    participant A as oauth2_authorization
    E->>S: findByToken(token, tokenType)
    S->>S: HMAC-SHA-256(tokenType, token)
    S->>L: SELECT authorization_id WHERE type + digest
    L-->>S: authorization_id
    S->>A: SELECT authorization WHERE id = ?
    A-->>S: Authorization row
    S-->>E: OAuth2Authorization
~~~

If `tokenType` is `null`, the custom service must preserve searching across all types supported by the implementation. It can compute digests for each token type and query by the set of `(token_type, token_hash)` pairs. Never query only one token type and return `null` when the token belongs to another type.

### 5.7. Limitations and Trade-Offs of a Lookup Table

A lookup table adds a mapping write per token, extra storage, and requires transactional consistency. When saving/updating an authorization, the custom service must update both the authorization row and lookup rows in the same transaction. When removing an authorization, delete matching mappings or use an appropriate foreign-key cascade.

A hash side table **does not automatically strip raw tokens from the authorization table**. If the goal is reducing raw token exposure in the database, design a persistence model that stores only digests and reconstructs token objects from requests/metadata per protocol needs. That is a major change to mappers/services and must be tested across all flows, including introspection, revocation, refresh, device flow, and OIDC.

If the HMAC key is rotated, support key versioning or a digest re-computation process. For example, add `hash_key_version` to the lookup table, dual-write during transition, backfill new digests, switch reads, and retire the old key. Losing an HMAC key means you can no longer compute digests to look up mappings created under that key.

## 6. Indexes for Queries Beyond Token Lookups

### 6.1. By RegisteredClient and Principal

Some systems have dashboards or admin tasks querying authorizations by client/principal:

~~~sql
CREATE INDEX idx_oauth2_auth_client_principal
    ON oauth2_authorization (registered_client_id, principal_name);
~~~

This index can assist a query like:

~~~sql
SELECT id, authorization_grant_type
FROM oauth2_authorization
WHERE registered_client_id = ?
  AND principal_name = ?;
~~~

It does not help default `findByToken` because token queries do not filter on those two columns. Create it only when the application actually runs matching query patterns.

If the workload primarily queries by `principal_name` without `registered_client_id`, a composite index starting with `registered_client_id` may not fit. Consider a dedicated index on `principal_name` after inspecting execution plans.

### 6.2. Consent Composite Key

The consent table's `(registered_client_id, principal_name)` primary key supports:

- Looking up consent by both client and principal.
- Looking up consents by client when the predicate uses the leading column.
- Deleting consent by the key pair.

If an admin page lists all clients granted permission by a principal, queries filtering by `principal_name` may need a dedicated index:

~~~sql
CREATE INDEX idx_oauth2_consent_principal
    ON oauth2_authorization_consent (principal_name);
~~~

Do not create this index if the application has no such query.

### 6.3. Cleanup by Expiry

Cleanup jobs may need to find expired authorizations. The table has columns such as:

- `authorization_code_expires_at`
- `access_token_expires_at`
- `refresh_token_expires_at`
- `oidc_id_token_expires_at`
- `user_code_expires_at`
- `device_code_expires_at`

If cleanup queries filter independently on specific expiry columns, dedicated indexes can help:

~~~sql
CREATE INDEX idx_oauth2_auth_access_expiry
    ON oauth2_authorization (access_token_expires_at);

CREATE INDEX idx_oauth2_auth_refresh_expiry
    ON oauth2_authorization (refresh_token_expires_at);
~~~

These are examples for cleanup jobs with matching predicates. Do not mechanically index every expiry column; inspect actual jobs and frequencies.

### 6.4. Never Delete an Authorization Just Because the Access Token Expired

An authorization row may hold a still-valid refresh token, an unexpired device/user code, or metadata needed for auditing. If the access token has expired while the refresh token remains valid, deleting the whole row breaks the refresh flow.

Cleanup jobs must evaluate the status of **all related tokens and authorizations**, including invalidated metadata and retention/audit policies. Deletions should run in bounded batches without holding long transactions.

## 7. How Does Data Size Affect Performance?

### 7.1. Long Tokens Enlarge Rows and LOBs

JWTs can be much longer than opaque tokens because they contain headers, claims, and signatures. ID Tokens can carry many claims; JWT access tokens can carry roles, tenants, permissions, or custom claims. When storing raw tokens in LOBs, longer tokens increase row footprint.

Size comes from more than just token values:

- `attributes` may store authorization requests, principals, or extra data.
- Token metadata holds issued/expiry timestamps, invalidated flags, and claims.
- OIDC ID Token claims may be serialized inside metadata.
- Scopes/authorities may grow per client.
- A single authorization row may contain multiple tokens at once.

### 7.2. Large Rows Increase Read Cost

When `findByToken` locates a row, `RowMapper` must read the relevant columns and reconstruct the domain object. If attributes/metadata/token values are very large:

- The database may have to fetch extra LOB pages.
- The network transfers more bytes from the database to the application.
- The JDBC driver must allocate buffers/streams for large payloads.
- JSON deserialization consumes CPU and memory allocations.
- Garbage collection faces pressure under high concurrency.

Indexes reduce the number of rows scanned, but do not shrink the matched row. That is why an indexed query can still be slow if authorization payloads are huge.

### 7.3. Wide Rows and Cache Locality

A table with many token/metadata columns produces wide rows. LOB data may live out-of-line from the main heap page depending on the database, yet still incurs extra pointers, page accesses, and I/O. Once the working set exceeds the buffer pool, the database must read pages from storage.

Indexes also occupy buffer cache. If token indexes are huge, cache space meant for data pages gets consumed by index pages. That is why fixed-size digest indexes are usually much smaller than raw JWT/token indexes.

### 7.4. Metadata Size Can Grow Unexpectedly

Do not store full user profiles, huge permission lists, or unnecessary request objects in `attributes`. Instead:

- Store only data required to continue the protocol flow.
- Use stable user IDs rather than serializing full profiles.
- Keep ID Token/access token claims minimal per audience and scope.
- Enforce size limits on requests/claims/attributes.
- Offload audit data or large business payloads to a suitable store.

Do not strip required metadata just to shrink row size. For example, invalidation metadata and claims needed for OIDC/token processing must be preserved per service semantics.

### 7.5. Serialization and LOB Handling

`JdbcOAuth2AuthorizationService` uses mappers to convert `OAuth2Authorization` into SQL parameters and `RowMapper` to rebuild objects. LOB columns are handled via `LobHandler`. With schemas using `BLOB`, text payloads may be converted into bytes; with `CLOB`/text, binding/reading differs.

Schemas must fit the database:

- PostgreSQL lacks `BLOB`; use appropriate text/bytea types matching content and SQL resources.
- Databases with row/index size caps require choosing compatible `VARCHAR`/LOB types.
- Verify timestamp timezone/instant semantics against the JDBC driver and DB.
- Fixed-length JSON columns may overflow with long attributes or metadata.

Do not change column data types arbitrarily without testing mappers, `LobHandler`, and schema migrations.

## 8. Optimizing the Authorization Write and Update Path

### 8.1. save May Read Before Writing

The default implementation checks `findById(authorization.getId())` to decide between insert and update. That adds an extra read on the save path. When an authorization flow performs multiple updates, read/write cost multiplies with the update count.

### 8.2. UPDATE Writes Many Columns

The default update SQL writes column groups for authorization, token values, issued/expires timestamps, and metadata. When a row has multiple LOBs, an update may serialize and bind substantial data even when the business change touches only one part.

Do not optimize by dropping columns required by the mappers. If write amplification becomes a bottleneck, consider a custom service/schema that updates only changed parts or splits token records into a dedicated model, while preserving transaction and object semantics.

### 8.3. Indexes Increase Write Amplification

When adding indexes on token values, expiries, client/principal, and lookup side tables, every issuance/refresh/revocation must maintain those indexes. Measure both read throughput and write throughput; never optimize introspection at the cost of making the Token Endpoint or refresh flow unacceptably slow.

## 9. Reading Execution Plans and Measuring Performance

### 9.1. Start from Real Queries

Before creating indexes:

1. Identify which endpoints/flows issue the query.
2. Capture exact SQL and parameter bind types.
3. Measure call frequency, hit/miss ratios, and token lengths.
4. Determine whether queries pass a token type or `null`.
5. Check row counts and data distribution.
6. Capture execution plans on production-scale data.

Never optimize based on a dev table containing a few hundred authorizations.

### 9.2. PostgreSQL EXPLAIN

For a custom schema with indexable token columns, e.g.:

~~~sql
PREPARE find_access_token(varchar) AS
SELECT id
FROM oauth2_authorization
WHERE access_token_value = $1;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE find_access_token('example-token-value');

DEALLOCATE find_access_token;
~~~

Inspect:

- Whether the planner chooses Index Scan/Bitmap Index Scan vs. Seq Scan.
- Estimated rows vs. actual rows.
- Actual time and loops.
- Shared hit/read buffers.
- Rows removed by filter.
- Heap fetches after index lookup.

Since default `findByToken` selects all authorization columns, the `id`-only query above is solely for examining the lookup path. Also test the service's actual `SELECT` statement because row materialization adds its own cost.

### 9.3. Measure Both Typed and Null tokenType

Benchmark both cases:

~~~sql
-- Known token type:
SELECT id
FROM oauth2_authorization
WHERE access_token_value = :token;

-- Unknown token type:
SELECT id
FROM oauth2_authorization
WHERE state = :token
   OR authorization_code_value = :token
   OR access_token_value = :token
   OR oidc_id_token_value = :token
   OR refresh_token_value = :token
   OR user_code_value = :token
   OR device_code_value = :token;
~~~

Compare execution plans and buffer reads. If unknown-token queries are on a hot path, a lookup table keyed by `(token_type, token_hash)` can give a custom service far better control over search plans.

### 9.4. Statistics and Maintenance

New indexes are not guaranteed to be chosen immediately if statistics are stale or data is skewed. After migrations/backfills, refresh statistics per database best practices. Monitor index bloat, dead tuples, vacuum/analyze runs, and growth. Unused indexes are pure write and storage overhead.

### 9.5. Benchmark Metrics

| Metric | Meaning |
| --- | --- |
| p50/p95/p99 latency | Typical and tail latency. |
| Queries per second | Lookup throughput. |
| Buffer hits/reads | Cache vs. storage read ratio. |
| Rows scanned/returned | Efficiency of the access path. |
| DB CPU | Cost of planning, comparisons, serialization, and row mapping. |
| Network bytes | Payload volume returned from DB to application. |
| Write latency | INSERT/UPDATE cost after adding indexes. |
| Index/table size | Storage footprint and cache pressure. |
| Lock waits/deadlocks | Contention across concurrent saves, revokes, and cleanups. |

Run tests with existing and missing tokens, uniform and skewed distributions, warm/cold caches, multiple clients, multiple token types, and production-like concurrency.

## 10. Data Cleanup and Retention

### 10.1. Expired Tokens Do Not Auto-Delete Rows

An expired token does not mean the authorization row can be deleted. The row may still contain a valid refresh token or data needed for logout/revocation/audits. `OAuth2Authorization.Token.isActive()` combines expiry and invalidated state; cleanup must account for both.

### 10.2. Batch Cleanup

At large scale, never delete millions of rows in a single transaction. A maintenance job should:

- Select a small batch of IDs in a stable order.
- Pick only rows past retention with no remaining tokens/authorizations needing preservation.
- Delete secondary mappings/indexes in the same transaction.
- Commit after each batch.
- Consider `SKIP LOCKED` if supported by the database and multiple cleanup workers run in parallel.
- Cap runtime, batch counts, and deletion rate.
- Emit metrics on rows inspected/deleted and processing duration.

Never run a `DELETE` conditioned solely on `access_token_expires_at < now()` if the row may still have an active refresh token or other valid tokens.

### 10.3. Workload-Driven Expiry Indexes

If cleanup frequently filters by `refresh_token_expires_at`, an index on that column can help. If the job filters on complex conditions spanning multiple token expiries and invalidation metadata, a single index may not suffice. Design index-friendly queries and check execution plans rather than creating indexes without evidence.

### 10.4. Retention and Security

Authorization data can hold bearer tokens, claims, and identifying information. Retention must balance:

- Ability to revoke/introspect active tokens.
- Refresh token rotation and reuse detection.
- Audit/security investigations.
- Data retention compliance rules.
- Storage/backup costs.
- Personal data deletion workflows.

Never retain tokens indefinitely merely for debugging convenience. Nor delete data prematurely while active tokens still depend on it.

## 11. When Is a Custom OAuth2AuthorizationService Needed?

### 11.1. Signs It Is Time to Replace the Implementation

Consider a custom service when:

- `findByToken` remains the main bottleneck despite proper indexes.
- The database cannot directly index token LOBs.
- Unknown token type queries produce overly expensive plans.
- Token hash/HMAC lookup or normalized token tables are needed.
- Authorization rows are too wide and `SELECT`ing all columns causes heavy I/O.
- Save/update write amplification fails throughput targets.
- Partitioning, sharding, or multi-tenant routing is required.
- Custom transaction/locking semantics are needed for refresh token rotation.

`JdbcOAuth2AuthorizationService` Javadoc recommends supplying a custom implementation when high-throughput requirements exceed the simplified implementation's limits.

### 11.2. Preserving the OAuth2AuthorizationService Contract

A custom implementation must preserve the semantics of all methods:

- `save(OAuth2Authorization)`
- `remove(OAuth2Authorization)`
- `findById(String)`
- `findByToken(String, OAuth2TokenType)`

Specifically:

1. `findByToken(token, null)` must search across all token types supported by the implementation.
2. `findByToken` must return the authorization holding the exact matching token, never an arbitrary row on digest collision/duplicate.
3. `save` must preserve token values, metadata, and invalidated state.
4. `remove` must delete lookup mappings and authorizations consistently.
5. Refresh/revocation/introspection must observe consistent state under the chosen transaction/consistency model.
6. Never leak tokens in logs, exceptions, or metrics.

### 11.3. Mappers and LobHandler

If keeping the LOB schema while customizing mappers:

- Keep JSON serialization compatible with Spring Security/Authorization Server Jackson modules.
- Ensure `LobHandler` binds/reads BLOB/CLOB properly.
- Test Unicode data, nested claims, and large payloads.
- Check column bounds and null handling.
- Ensure timestamps/`Instant`s round-trip accurately across timezones.

If splitting token tables, ensure full transaction handling and migrations; do not add an auxiliary repository while leaving the default service querying the old table.

## 12. Common Pitfalls and Resolutions

### Pitfall 1: Adding an index yet queries still full-scan

**Symptom:** Index exists, yet the execution plan still uses Seq Scan/Table Scan.

**Cause:** LOB column type, incompatible predicate, low selectivity, stale statistics, or non-covering index.

**Resolution:** Check data types, actual SQL, bind types, and execution plans; consider digest lookups if LOBs cannot be indexed.

### Pitfall 2: Creating a prefix index for tokens

**Symptom:** Many candidate rows share a prefix, or the database still filters many rows.

**Cause:** Prefixes are not unique and do not represent the full token.

**Resolution:** Use full-value equality where viable or a fixed-size HMAC digest; always verify the entire token.

### Pitfall 3: Assuming a hash column automatically speeds up the default service

**Symptom:** Added `access_token_hash`, yet queries remain slow.

**Cause:** `JdbcOAuth2AuthorizationService` still executes `WHERE access_token_value = ?`.

**Resolution:** Customize the mapper/write path and `findByToken` to query the digest; or use a side table with a custom service.

### Pitfall 4: Creating too many indexes

**Symptom:** Read queries get faster, yet Token Endpoint/refresh/revoke slow down and storage grows.

**Cause:** Index write amplification and buffer pressure.

**Resolution:** Keep only indexes serving measured workloads; benchmark both reads and writes.

### Pitfall 5: Optimizing token lookup while ignoring row size

**Symptom:** Query plan uses an index, yet latency remains high.

**Cause:** `RowMapper` reads large LOBs, deserializes attributes/claims, and builds objects.

**Resolution:** Trim unnecessary payloads, cap claims/attributes, or consider a specialized schema/service.

### Pitfall 6: Using an expiry index to delete every row with an expired access token

**Symptom:** Refresh tokens are still valid, yet authorizations get deleted.

**Cause:** Cleanup inspects only one token in the row.

**Resolution:** Evaluate all tokens and retention policies before deleting.

### Pitfall 7: Using plain SHA-256 for short user codes

**Symptom:** Anyone with a database copy can guess user codes offline.

**Cause:** Unkeyed hash combined with low-entropy input.

**Resolution:** Use HMAC with a key external to the DB, rate limiting, and key version management.

### Pitfall 8: Lookup table not updated together with the authorization

**Symptom:** Token exists in authorization yet no mapping is found, or mapping points to a deleted row.

**Cause:** Writing two tables in separate transactions or missing update/remove branches.

**Resolution:** Maintain mappings atomically, use matching foreign keys/cascades, and run reconciliation jobs.

### Pitfall 9: Wrong column order in a composite index

**Symptom:** Queries by principal fail to use the `(registered_client_id, principal_name)` index.

**Cause:** Predicate omits the leading key column.

**Resolution:** Order columns to match actual equality/sort predicates and inspect plans.

### Pitfall 10: Benchmarking with tiny datasets

**Symptom:** Local tests fly, yet production crawls.

**Cause:** Failed to simulate cardinality, skew, token lengths, concurrency, and cache pressure.

**Resolution:** Benchmark on production-scale data and measure p95/p99, buffer reads, and write latency.

## 13. Test and Benchmark Matrix

| Case | Expected outcome |
| --- | --- |
| `findById` with existing ID | Uses PK lookup and returns the right authorization. |
| `findByToken` with access token type | Filters on the exact access token column. |
| `findByToken` with refresh token type | Filters on the exact refresh token column. |
| `findByToken` with authorization code type | Filters on the exact code column. |
| `findByToken` with null `tokenType` | Searches all supported token/state types per contract. |
| Non-existent token | Returns `null` with stable latency. |
| Tokens sharing prefix but differing values | Never returns the wrong authorization. |
| Token near max length | Insert, lookup, and row mapping succeed. |
| Large metadata/attributes | No truncation; JSON round-trips cleanly. |
| BLOB/CLOB LOBs | Mappers read/write properly per DB schema. |
| Direct index on token | Execution plan uses index when appropriate. |
| Hash lookup | Digest computed consistently and query returns right ID. |
| HMAC key version rotation | Both old/new mappings work during transition. |
| Save/update authorization | Lookup mappings and data rows stay in sync. |
| Remove authorization | Auxiliary mappings deleted cleanly. |
| Refresh token rotation | Old token invalidated, new token looked up accurately. |
| Revocation | Locates right authorization and updates invalidation metadata. |
| Cleanup batch | Never deletes rows with active refresh/device/user tokens. |
| Consent lookup by client + principal | Composite PK is used. |
| Consent lookup by principal | Dedicated index exists if workload requires it. |
| Concurrent lookups/writes | No lost mappings or inconsistent state reads. |
| Multi-million-row load test | p95/p99 meet SLOs, query plans remain stable. |

### 13.1. Before/After Index Benchmark Workflow

1. Generate a dataset with production-like cardinality and token type distribution.
2. Run typed and `tokenType=null` queries to establish a baseline.
3. Record execution plans, p50/p95/p99, buffer reads, and DB CPU.
4. Create a small set of indexes targeting hot-path queries.
5. Refresh statistics and re-run benchmarks.
6. Measure Token Endpoint/refresh/revoke write paths too.
7. Measure index storage size and maintenance cost.
8. Keep only changes delivering net overall gain with a rollback plan.

## 14. Production Checklist

| Item | Condition to confirm |
| --- | --- |
| Schema | Schema matches exact Spring Authorization Server version and DB vendor? |
| Token lookup | Known which endpoints call `findByToken` and at what frequency? |
| Token type | Callers pass token type when known; `null` still preserves full semantics? |
| Primary key | `id` has a PK/index? |
| Secondary indexes | Indexes created strictly per query workload on indexable column types? |
| LOBs | Verified BLOB/CLOB indexability and size limits? |
| Hash lookup | Custom service actually queries the digest rather than just adding a column? |
| HMAC key | Secret key stored outside DB with a rotation plan? |
| Row size | Attributes/claims/metadata bounded without excess payloads? |
| Write path | Measured `save`/update cost and index maintenance? |
| Consent | Composite PK fits query patterns? |
| Cleanup | Deletes rows only once all related tokens are expired/invalidated and retention permits? |
| Query plans | Verified `EXPLAIN`/`ANALYZE` and up-to-date statistics? |
| Benchmarks | Measured p95/p99, reads/writes, hits/misses, and concurrency? |
| Custom service | Preserves full `OAuth2AuthorizationService` contract? |
| Consistency | Authorization and token lookup mappings updated in the same transaction? |
| Observability | Metrics exist for query latency, rows/buffers, DB pool wait, and table/index growth? |
| Security | Raw bearer tokens or HMAC secrets never logged? |

## 15. Hands-On Exercise

An Authorization Server holds 8 million rows in `oauth2_authorization`. Roughly 70% of requests look up access tokens, 20% look up refresh tokens, and the remaining 10% look up codes, ID Tokens, user codes, or device codes. The schema uses `BLOB` for token values; the table has PK `id` but no secondary indexes. Some authorization rows have long attributes/claims from storing excessive profile data.

1. Diagram the query path for `findByToken(token, tokenType)` for access token, refresh token, and null token type.
2. Explain why an index on `access_token_expires_at` does not help `WHERE access_token_value = ?`.
3. Propose indexes if the database/schema moves token columns to full-value indexable types; list the limitations of this approach.
4. Design `oauth2_authorization_token_lookup` with HMAC-SHA-256 and a composite primary key.
5. Write pseudocode for `findByToken` with a specific token type and with null token type.
6. Prove why adding a hash column without changing SQL does not make default queries use the hash index.
7. Measure the impact of row size by trimming unnecessary attributes/claims.
8. Design a cleanup batch that never deletes authorizations with active refresh tokens.
9. Compare p95/p99, buffer reads, and write latency before and after indexing.
10. Define decision criteria for keeping `JdbcOAuth2AuthorizationService` vs. replacing it with a custom implementation.

**Passing Criteria:** Index design matches actual queries without relying on unsupported LOB indexes, token lookup digests stay consistent, cleanup never breaks valid tokens, and benchmarks demonstrate both read gains and write costs.

## 16. Reference Documentation

- [Spring Authorization Server 1.5.8 — JdbcOAuth2AuthorizationService Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/JdbcOAuth2AuthorizationService.html): schema dependency, `findById`, `findByToken`, mappers, and throughput limits of the default JDBC implementation.
- [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `OAuth2Authorization` structure, token lifecycle, and `OAuth2AuthorizationService`.
- [Spring Authorization Server 1.5.8 — How-to: Implement core services with JPA](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-jpa.html): flattened authorization schema, consent composite key, repository queries, and data size notes.
- [Spring Authorization Server — oauth2-authorization-schema.sql](https://github.com/spring-attic/spring-authorization-server/blob/main/oauth2-authorization-server/src/main/resources/org/springframework/security/oauth2/server/authorization/oauth2-authorization-schema.sql): authorization columns and primary key of the JDBC schema.
- [Spring Authorization Server — oauth2-authorization-consent-schema.sql](https://github.com/spring-attic/spring-authorization-server/blob/main/oauth2-authorization-server/src/main/resources/org/springframework/security/oauth2/server/authorization/oauth2-authorization-consent-schema.sql): composite primary key of authorization consent.
- [PostgreSQL — Indexes](https://www.postgresql.org/docs/current/indexes.html): how indexes support equality/range lookups and write cost trade-offs.
- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): reading execution plans and estimated/actual costs.
- [PostgreSQL — Index Types](https://www.postgresql.org/docs/current/indexes-types.html): B-tree, hash, GIN, GiST, and usage scope.
- [MySQL — InnoDB Limits](https://dev.mysql.com/doc/refman/8.4/en/innodb-limits.html): row size and index key length limits.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): token endpoint, refresh tokens, and authorization lifecycle.
