# Adding Auditing, Row-Level Authorization, and Sensitive Data Protection

## 1. Three responsibilities that must be designed separately

A Spring Data Relational R2DBC application often needs to record who created or modified data, restrict which records a user may access, and protect fields holding sensitive information. These three requirements relate to one another, yet none replaces the others:

- **Auditing** records lifecycle metadata such as creator, creation time, last modifier, and last modification time.
- **Row-level authorization** determines which specific records a user or service is permitted to read, update, or delete.
- **Sensitive data protection** limits the collection, storage, transmission, exposure, and logging of protected data.

For example, a document record may contain:

- `created_by`, `created_at`, `updated_by`, `updated_at`: auditing metadata.
- `tenant_id`, `owner_id`: fields used to determine access scope.
- `customer_email`, `tax_number`, `private_note`: data requiring policy-based protection.

Having `created_by` does not mean the creator is the only user allowed to read the record. Having `tenant_id` does not automatically ensure every query filters by the right tenant. Database encryption does not replace authorization. Each layer must be enforced and tested independently.

## 2. Overall architecture

Processing can be structured as follows:

~~~text
Authenticated request / trusted job
              |
              v
      Security identity + tenant
              |
              v
       Service authorization
       - actor is authenticated
       - tenant / owner scope
       - business permission
              |
              v
       Repository / DatabaseClient
       - scoped SELECT / UPDATE / DELETE
       - auditing callbacks
              |
              v
         R2DBC ConnectionFactory
              |
              v
            Database
       - constraints / optional RLS
       - least-privilege database role
              |
              v
       Protected data + audit metadata
              |
              v
       DTO / response projection
       - expose allowed fields only
       - redact sensitive values
~~~

This flow provides defense in depth. The service identifies the actor and business permissions; queries scope rows; database constraints guard integrity; Row-Level Security (RLS), when used, adds a database-layer control; and DTOs govern which fields leave the server.

Never place all access checks solely in the controller or rely on the UI hiding an edit button. Any request can be sent directly to the API. Permissions must be verified on the server and across every relevant data access path.

## 3. Auditing in Spring Data R2DBC

Spring Data R2DBC supports auditing metadata through Spring Data annotations:

| Annotation | Meaning |
|---|---|
| `@CreatedBy` | Actor who created the record |
| `@CreatedDate` | Creation timestamp |
| `@LastModifiedBy` | Actor who last modified the record |
| `@LastModifiedDate` | Last modification timestamp |

These annotations live in `org.springframework.data.annotation`. Auditing is enabled via `@EnableR2dbcAuditing`. When retrieving the actor from the reactive security context, provide a `ReactiveAuditorAware<T>` bean.

Auditing answers questions such as:

- Who created this record?
- When was it created?
- Who modified it most recently?
- When did the last modification occur?

It does not automatically store a full change history. `@LastModifiedBy` records only the most recent actor, not every historical editor or before/after values for each change.

### 3.1. Declaring auditing metadata on an entity

Immutable entity example:

~~~java
@Table("documents")
public record Document(
        @Id Long id,
        String title,
        String body,
        UUID tenantId,
        UUID ownerId,
        @CreatedBy String createdBy,
        @CreatedDate Instant createdAt,
        @LastModifiedBy String updatedBy,
        @LastModifiedDate Instant updatedAt,
        @Version Long version
) {}
~~~

The fields play distinct roles:

- `tenantId` identifies the owning tenant.
- `ownerId` identifies the business owner when the model has an owner concept.
- `createdBy` and `updatedBy` record actors.
- `createdAt` and `updatedAt` record timestamps.
- `version` supports optimistic locking per Spring Data R2DBC configuration.

Do not substitute `createdBy` for `ownerId` if business rules allow someone to create a record on another owner's behalf. For instance, a support agent may create a profile for a customer; the creating actor and the record owner are two different people.

For mutable entities, auditing fields can likewise be declared as properties. Ensure constructor/property access and types match your mapping configuration.

### 3.2. Enabling R2DBC auditing

Basic configuration:

~~~java
@Configuration
@EnableR2dbcAuditing
class R2dbcAuditingConfiguration {
}
~~~

To supply a custom auditor, reference the bean:

~~~java
@Configuration
@EnableR2dbcAuditing(auditorAwareRef = "auditorProvider")
class R2dbcAuditingConfiguration {

    @Bean
    ReactiveAuditorAware<String> auditorProvider() {
        return () -> ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .filter(Authentication::isAuthenticated)
                .map(Authentication::getName)
                .filter(name -> !"anonymousUser".equals(name));
    }
}
~~~

Key imports typically come from:

- `org.springframework.data.domain.ReactiveAuditorAware`
- `org.springframework.data.r2dbc.config.EnableR2dbcAuditing`
- `org.springframework.security.core.Authentication`
- `org.springframework.security.core.context.SecurityContext`
- `org.springframework.security.core.context.ReactiveSecurityContextHolder`

This snippet assumes reactive Spring Security. If your application authenticates differently, implement `ReactiveAuditorAware` against your system's trusted actor context.

`ReactiveAuditorAware` returns `Mono<T>`. If no actor is present, it may return `Mono.empty()`. Auditing actor fields then remain unset, so define that behavior explicitly with your schema and business rules. Never default every unauthenticated request to a single fallback user, as that destroys traceability.

### 3.3. Never accept the actor from request bodies or arbitrary headers

Auditing actors must come from a server-verified identity. Never use client-supplied `createdBy` values in JSON or unverified `X-User-Id` headers.

If clients can supply their own actor ID, they can attribute creates or edits to someone else. This corrupts the audit trail and can undermine security decisions.

A trustworthy flow typically looks like:

1. An authentication filter verifies credentials or tokens.
2. Spring Security places `Authentication` into the reactive security context.
3. Service/repository auditing reads the actor from that context.
4. Clients have no control over `createdBy` or `updatedBy`.

If your system supports legitimate impersonation, record both the acting user and the impersonated subject separately, along with reason/authorization metadata. Never overwrite the identity of the person actually performing the action.

## 4. Reactive Security Context and AuditorAware

In WebFlux applications, execution can switch threads. Never rely on `ThreadLocal` or imperative `SecurityContextHolder` to resolve the actor inside reactive pipelines.

`ReactiveSecurityContextHolder` reads `SecurityContext` from the Reactor Context. This integrates cleanly with `ReactiveAuditorAware`, as the auditor resolves within the reactive flow.

Core principles:

- Never call `block()` to fetch `Authentication` inside an auditor.
- Never call `subscribe()` separately to read the actor.
- Never store the actor in a mutable field shared across requests.
- Never depend on the current thread to identify the user.
- Verify the context propagates through custom operators and boundaries.

Example resolving the actor in a service:

~~~java
public Mono<String> currentActor() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .map(Authentication::getName);
}
~~~

The auditor is invoked automatically when Spring Data maps and saves entities. When code runs outside HTTP requests—such as scheduled jobs or message consumers—define an explicit system actor.

### 4.1. Background jobs and service accounts

Background jobs typically have no user session. Never assume `ReactiveSecurityContextHolder` is always populated.

Define a dedicated actor for the job, such as `service:invoice-reconciler`, and attach it to the context in a controlled way. One option is creating an `Authentication` representing the service account and applying `ReactiveSecurityContextHolder.withAuthentication(...)` around the job publisher. Another option is a dedicated actor context read by `ReactiveAuditorAware`.

What matters is that the recorded actor reflects the real execution source:

- Authenticated human user.
- Service account.
- Scheduled job.
- Message consumer.
- Migration or operations system.

Never attribute all non-user work to one generic admin account if accurate attribution matters. You can also record `actor_type` and job/message identifiers in a dedicated audit event.

## 5. Auditing timestamps and timezones

Pick a consistent time type, typically `Instant` for absolute points in time. Store timestamps in UTC and convert to a user's timezone only for display.

Example entity fields:

~~~java
@CreatedDate
Instant createdAt;

@LastModifiedDate
Instant updatedAt;
~~~

With PostgreSQL schemas, `TIMESTAMPTZ` is usually appropriate for absolute timestamps. Confirm type mappings with your driver and database SQL types.

Decisions to make:

- Which clock supplies timestamps: application or database?
- Is clock synchronization across instances needed?
- What timestamp precision does the database preserve?
- Do tests need to assert creation and update timestamps?
- When importing legacy data, are original timestamps preserved?

In tests, configure an appropriate clock or date/time provider when deterministic timestamps are needed. Avoid comparing formatted timestamp strings that depend on the host's default timezone.

## 6. Auditing metadata is not a complete audit trail

Entity auditing metadata retains only the current `created` and `modified` fields. When full change history is required, design a dedicated audit trail.

An audit event may include:

| Field | Meaning |
|---|---|
| `event_id` | Unique ID of the event |
| `occurred_at` | Timestamp when the event occurred |
| `actor_id` | User or service performing the action |
| `actor_type` | User, service, job, or system |
| `action` | `CREATE`, `UPDATE`, `DELETE`, `EXPORT`, or domain action |
| `resource_type` | Resource category |
| `resource_id` | Resource identifier |
| `tenant_id` | Tenant scope |
| `correlation_id` | Link to request/trace |
| `reason` | Justification if required by business rules |
| `change_summary` | Redacted summary of what changed |

Example:

~~~json
{
  "eventId": "a7f8...",
  "occurredAt": "2026-11-15T10:30:00Z",
  "actorId": "user-42",
  "actorType": "USER",
  "action": "DOCUMENT_UPDATED",
  "resourceType": "DOCUMENT",
  "resourceId": "doc-900",
  "tenantId": "tenant-7",
  "correlationId": "req-abc",
  "changeSummary": {
    "title": {
      "changed": true
    },
    "body": {
      "changed": true,
      "value": "[REDACTED]"
    }
  }
}
~~~

This illustrates structure only. Never write literal passwords, tokens, secrets, sensitive record contents, or unnecessary personal data into audit events.

If the audit trail must not be altered or deleted by the application runtime, use an append-only table where the runtime role has only `INSERT`/`SELECT` privileges, while `UPDATE`/`DELETE` are restricted to controlled operational roles. For stronger tamper resistance, add immutable or tamper-evident storage per organizational policy.

## 7. Writing audit events consistently with transactions

When an audit event is mandatory evidence of a business change, define the relationship between primary data and the audit event.

For instance, if a document update commits while the audit event is lost, history is incomplete. Conversely, if the audit event is written first and the document update rolls back, the trail records a change that never occurred.

A common pattern writes business data and an audit/outbox event in the same database transaction:

~~~text
Reactive transaction
       |
       +--> UPDATE documents
       |
       +--> INSERT audit_outbox
       |
       v
     COMMIT
       |
       v
Background publisher reads outbox
       |
       v
Append audit event / publish downstream
~~~

If the audit table lives in the same database and must be atomic with the record, write both in the same reactive transaction. When shipping events to an external system, a transactional outbox prevents transaction success from depending on an external network call.

Never send HTTP requests or publish broker messages directly inside entity callbacks assuming they are atomic with commit. Pre/post-save callbacks do not guarantee messages are emitted only after commit.

## 8. What is row-level authorization?

Endpoint-level authorization answers "Can this user invoke this endpoint?". Row-level authorization additionally answers "Is this user permitted to act on this specific record?".

For example, two users both hold the `document:read` permission, yet each may only view documents belonging to their own tenant or owner scope.

Common scopes:

- **Tenant scope:** access only records belonging to the current tenant.
- **Owner scope:** access only records owned by the user.
- **Team/organization scope:** access records assigned to authorized teams or units.
- **Relationship scope:** access only records linked validly to the user, such as an agent assigned to a case.
- **Administrative scope:** actors with elevated privileges whose actions must be explicitly audited.

Never treat `id` as a secret. An unguessable ID does not replace authorization. If an API receives `/documents/900`, the server must still verify the user has rights to document 900.

This prevents Insecure Direct Object Reference (IDOR) vulnerabilities, where a user swaps an ID in a URL or body to read or modify someone else's record.

## 9. Embedding tenant and owner scope in queries

A clear pattern defines repository methods scoped by tenant/owner:

~~~java
public interface DocumentRepository
        extends ReactiveCrudRepository<Document, Long> {

    Mono<Document> findByIdAndTenantId(
            Long id,
            UUID tenantId
    );

    Flux<Document> findAllByTenantIdAndOwnerId(
            UUID tenantId,
            UUID ownerId
    );
}
~~~

The service resolves tenant and actor from a trusted context and passes them to the query:

~~~java
public Mono<Document> findDocument(Long id) {
    return currentTenantId()
            .flatMap(tenantId ->
                    documentRepository.findByIdAndTenantId(id, tenantId)
            );
}
~~~

For owner-scoped access, add the owner ID or verify the corresponding permission:

~~~java
public Mono<Document> findOwnedDocument(Long id) {
    return currentTenantId()
            .zipWith(currentUserId())
            .flatMap(tuple ->
                    documentRepository.findByIdAndTenantIdAndOwnerId(
                            id,
                            tuple.getT1(),
                            tuple.getT2()
                    )
            );
}
~~~

`currentTenantId()` and `currentUserId()` are abstractions reading from the application's security context/tenant resolver. Never trust a tenant ID taken straight from a request body. If a request carries a tenant selector, verify the user is authorized to operate in that tenant first.

Scoped queries make the database return only in-scope rows, reducing the risk of accidentally loading another tenant's row and forgetting a post-load check.

### 9.1. Never use unscoped findById in multi-tenant flows

A frequent pitfall:

~~~java
return documentRepository.findById(id)
        .flatMap(document -> authorize(document));
~~~

This loads the row before checking permissions. Even if every branch checks properly today, it is easy to miss a branch, log statement, or response path later. For multi-tenant data, prefer scoped queries:

~~~java
return documentRepository.findByIdAndTenantId(id, tenantId)
        .switchIfEmpty(Mono.error(new DocumentNotFoundException()));
~~~

Apply the same discipline to `SELECT`, `UPDATE`, `DELETE`, counts, exports, and bulk operations—not just detail read endpoints.

### 9.2. Avoid leaking record existence

When a user lacks access, return `404` if your policy avoids revealing whether a record exists, or `403` if your API contract explicitly signals denial. Align this across your security and API design.

Crucially, never include record content, tenant IDs, owner IDs, or sensitive fields in error messages. Internal logs may record denial reasons in a controlled manner, never exposed in public responses.

## 10. Protecting UPDATE and DELETE with scope predicates

Not only `SELECT` needs tenant/owner predicates—`UPDATE` and `DELETE` must include scope conditions too.

Example `DatabaseClient` update:

~~~java
public Mono<Integer> renameDocument(
        Long id,
        UUID tenantId,
        UUID ownerId,
        String title) {

    return databaseClient.sql("""
            UPDATE documents
            SET title = :title,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
              AND tenant_id = :tenantId
              AND owner_id = :ownerId
            """)
            .bind("title", title)
            .bind("id", id)
            .bind("tenantId", tenantId)
            .bind("ownerId", ownerId)
            .fetch()
            .rowsUpdated();
}
~~~

Handle the affected row count explicitly:

- `1`: one row updated.
- `0`: row does not exist or falls outside scope; avoid disclosing which if policy hides existence.
- Error: handle according to database/driver error and retry policies.

Use bind parameters for all values. Never concatenate `title`, `id`, or `tenantId` inputs into SQL strings.

Apply the same predicates to `DELETE`:

~~~sql
DELETE FROM documents
WHERE id = :id
  AND tenant_id = :tenantId
  AND owner_id = :ownerId
~~~

Audit every native query carefully, because hand-written SQL bypasses standard repository method conventions.

## 11. Centralizing authorization to avoid missing predicates

As repositories grow, repeating tenant/owner predicates across every service invites omissions. Establish structural safeguards:

- Service methods require a verified `AuthorizedTenant` or scope context object.
- Custom repository fragments expose only scoped methods.
- Shared base repositories cover common scoped operations.
- Query builders inject mandatory tenant predicates automatically.
- Database RLS adds a secondary defense layer.
- Integration tests exercise `SELECT`/`UPDATE`/`DELETE` paths.

Example type representing a verified scope:

~~~java
public record AccessScope(
        UUID tenantId,
        UUID actorId,
        Set<String> permissions
) {}
~~~

Never construct `AccessScope` directly from client input. An authentication/authorization component must build it after verifying the principal and permissions.

Avoid exposing both an unrestricted `findById(id)` and scoped methods on a public repository interface and expecting developers to remember which is safe. Restrict repository visibility, wrap behind a facade, or enforce strict code-review rules.

## 12. Tenant isolation and data integrity

In multi-tenant schemas, an ordinary foreign key ensures the referenced row exists, not that both rows belong to the same tenant.

For example, if both `documents` and `document_comments` carry `tenant_id`, use a composite unique key and composite foreign key so comments can only reference documents in the same tenant:

~~~sql
ALTER TABLE documents
ADD CONSTRAINT uq_documents_tenant_id_id
UNIQUE (tenant_id, id);

ALTER TABLE document_comments
ADD CONSTRAINT fk_comments_document_tenant
FOREIGN KEY (tenant_id, document_id)
REFERENCES documents (tenant_id, id);
~~~

This enforces isolation at the schema level. If application code attempts to insert a comment for tenant A pointing at a document owned by tenant B, the database rejects it.

Design indexes to align with scoped queries:

~~~sql
CREATE INDEX ix_documents_tenant_owner_updated
ON documents (tenant_id, owner_id, updated_at DESC);
~~~

Actual indexes depend on workload, selectivity, and query plans; measure rather than adding indexes blindly. For per-tenant unique business keys, use composite unique constraints `(tenant_id, business_key)` when dictated by business rules.

## 13. PostgreSQL Row-Level Security (RLS)

Beyond service and query authorization, PostgreSQL offers Row-Level Security to restrict which rows a database role can read or modify.

Example enabling RLS:

~~~sql
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents FORCE ROW LEVEL SECURITY;

CREATE POLICY documents_tenant_policy
ON documents
USING (
    tenant_id = current_setting('app.tenant_id', true)::uuid
)
WITH CHECK (
    tenant_id = current_setting('app.tenant_id', true)::uuid
);
~~~

Meaning:

- `USING` restricts which existing rows are visible or modifiable.
- `WITH CHECK` enforces that new or updated rows satisfy the policy.
- `current_setting(..., true)` returns `NULL` when unset; the comparison yields unknown and permits no rows.
- `FORCE ROW LEVEL SECURITY` applies the policy even to the table owner in normal cases, though superusers and roles with `BYPASSRLS` still bypass RLS.

Use a runtime database role that is neither a superuser nor granted `BYPASSRLS`. If the runtime role owns the table, understand owner/RLS interaction and test directly under the runtime role.

### 13.1. Setting tenant context inside the transaction

Set the tenant using a transaction-local setting before querying:

~~~java
Mono<Map<String, Object>> setTenant =
        databaseClient.sql("""
                SELECT set_config('app.tenant_id', :tenantId, true)
                """)
                .bind("tenantId", tenantId.toString())
                .fetch()
                .one();

Mono<List<Document>> work =
        setTenant.thenMany(documentRepository.findAll())
                .collectList();

return transactionalOperator.transactional(work);
~~~

Adapt the return types and repository APIs to your project. Crucially, `set_config(..., true)` sets the configuration only for the current transaction. Both the context-setting statement and protected queries must run inside the same transaction and connection.

Never use persistent session-level settings on pooled connections. If tenant A sets a session variable and the connection returns to the pool for tenant B, the stale tenant context can leak across requests. Transaction-local settings mitigate this because they clear when the transaction ends.

Never set the tenant on one connection and query on another. With connection pooling, two separate acquisitions are not guaranteed to receive the same connection. Set and consume context inside the same reactive transaction.

### 13.2. RLS is defense in depth, not an excuse to drop query scopes

RLS catches queries that accidentally omit a tenant predicate, yet you still need application-layer authorization to enforce business permissions, owners, teams, and actions.

Keep in mind:

- PostgreSQL combines multiple permissive policies with `OR`; restrictive policies combine with `AND`.
- Privileged roles can bypass RLS.
- Table owners behave differently unless `FORCE` RLS is enabled.
- Migration/admin roles typically hold different privileges than runtime roles.
- Views, functions, partitions, and related tables must be evaluated separately.
- Background jobs must set tenant context explicitly.
- Tests must run as the actual runtime role.

When using multiple tenant policies, verify how they combine so you never accidentally broaden access. RLS complements, rather than replaces, schema reviews, role design, and application authorization.

## 14. Protecting sensitive data at the API layer

Never return database entities directly from APIs if they contain internal or sensitive fields.

Use a response DTO exposing only necessary fields:

~~~java
public record DocumentResponse(
        Long id,
        String title,
        String bodyPreview,
        Instant createdAt,
        String ownerDisplayName
) {}
~~~

DTO mapping:

~~~java
public Mono<DocumentResponse> getDocument(Long id) {
    return authorizedDocument(id)
            .map(document -> new DocumentResponse(
                    document.id(),
                    document.title(),
                    preview(document.body()),
                    document.createdAt(),
                    resolveOwnerDisplayName(document.ownerId())
            ));
}
~~~

This illustrates an explicit allowlist. Never expose `tenantId`, internal notes, access tokens, secrets, or unnecessary personal data in responses.

`@JsonIgnore` helps with serialization, but is not a complete authorization mechanism. Another endpoint, log serializer, or mapper could still expose the field. Explicit DTOs control the contract cleanly.

For sensitive fields, consider:

- Returning them only when the caller holds a specific permission.
- Partially masking values when full values are unnecessary.
- Omitting them from default list/detail responses.
- Separating high-privilege endpoints.
- Applying the same rules to exports, downloads, and bulk APIs.

## 15. Encryption, hashing, and tokenization

Different categories of sensitive data require different protections.

| Data type | Typically suitable protection |
|---|---|
| Passwords | Salted one-way password hash such as Argon2id or BCrypt |
| Verifiable API keys/secrets | Store a hash or HMAC if recovery of the original value is not needed |
| Readable PII | Reversible encryption with separate key management |
| Exact-lookup identifiers | Consider a separate HMAC/blind index, evaluating equality leakage |
| Payment data | Tokenization and specialized compliant services per system rules |
| Unneeded data | Do not collect, or purge per retention policy |

Hashing and encryption are distinct:

- One-way hashing suits verification when the original value never needs to be recovered.
- Reversible encryption allows decryption and requires strict key management and access control.
- Tokenization replaces sensitive values with tokens while keeping raw values in an isolated system.

Never store passwords with reversible encryption. Never use MD5, SHA-1, or fast unsalted hashes for password storage.

### 15.1. Encryption in transit and at rest

Layers to evaluate:

- TLS between clients and the API.
- TLS between the application and the database where environment policies require it.
- Storage/database encryption at rest.
- Application-level field encryption for fields with specialized requirements.
- Key management via KMS, HSM, or a secret manager.
- Key rotation and versioning.

Encryption at rest does not stop a user authorized through the application from reading plaintext that the application decrypts. Authorization and field-level access controls remain essential.

### 15.2. Managing encryption keys

Never store encryption keys alongside ciphertext in the same table or in source code. With envelope encryption, the application uses a data encryption key to encrypt data and a key encryption key in KMS to protect the data key.

Define clearly:

- Who may request decryption?
- How does key rotation work?
- When is older data re-encrypted?
- How does the application behave if KMS is temporarily unavailable?
- Do backups and restores preserve decryption capability?
- Is every key access audited?

Losing keys renders encrypted data unrecoverable. Key management and backup/restore must be tested as part of operational readiness.

## 16. Protecting sensitive fields while supporting search

Standard randomized encryption produces different ciphertexts for identical plaintexts, preventing simple equality index lookups. Deterministic encryption or blind indexes enable certain lookups, at the cost of leaking equality and frequency information.

One pattern stores ciphertext alongside a separate HMAC/blind index:

~~~text
sensitive_value_ciphertext
sensitive_value_lookup_hmac
encryption_key_version
~~~

Lookup HMACs must use a dedicated key and consistent canonicalization. Never reuse the encryption key as the HMAC key. Evaluate dictionary-guessing risks if the value domain is small, such as region codes or statuses.

Do not design custom searchable encryption merely to keep legacy query patterns unchanged. First assess genuine search needs, the threat model, and acceptable leakage. Use tokenization or specialized services when requirements are complex.

## 17. SQL injection and dynamic queries

R2DBC supports bind parameters. Always bind data values:

~~~java
return databaseClient.sql("""
        SELECT id, title
        FROM documents
        WHERE tenant_id = :tenantId
          AND owner_id = :ownerId
          AND status = :status
        """)
        .bind("tenantId", tenantId)
        .bind("ownerId", ownerId)
        .bind("status", status)
        .fetch()
        .all();
~~~

Never concatenate input directly into SQL:

~~~java
// Never do this:
String sql = "SELECT * FROM documents WHERE title = '" + title + "'";
~~~

Bind parameters cannot substitute for table names, column names, or SQL keywords. For dynamic sorting, map client choices through an allowlist of permitted identifiers:

~~~java
String orderColumn = switch (sortField) {
    case "createdAt" -> "created_at";
    case "title" -> "title";
    default -> "created_at";
};
~~~

Only insert identifiers from an internal allowlist. Never pass raw `sortField` into SQL, and ensure tenant/owner predicates always remain present in constructed queries.

## 18. Protecting information in logs, traces, and metrics

Data can leak outside API responses, especially through logs and observability pipelines.

Never log:

- Passwords, access tokens, refresh tokens, or API keys.
- Session cookies or `Authorization` headers.
- Full payment credentials.
- PII content unnecessary for troubleshooting.
- Entire request/response bodies by default.
- Sensitive bind parameters.
- Ciphertext alongside keys or material sufficient to decrypt it.

Logs should capture the operation and necessary metadata:

~~~text
event=document.read
actor_id=user-42
tenant_id=tenant-7
resource_id=doc-900
outcome=denied
correlation_id=req-abc
~~~

This shows log structure only. Record identifiers only when permitted by data policy; pseudonymized IDs or correlation tokens can be used instead.

Metrics require low-cardinality tags. Never use emails, user IDs, unbounded tenant IDs, or resource IDs as metric labels. Traces can carry correlation IDs, provided access control and retention on the tracing backend are properly restricted.

Check exception logging carefully too. Exceptions can carry SQL, bind values, or payload snippets. Avoid dumping full objects or sensitive stack contexts to broadly accessible log sinks.

## 19. Database roles and least privilege

The application runtime should connect using a database role with only the minimum privileges required.

Example role separation:

| Role | Typical privileges |
|---|---|
| `app_runtime` | `SELECT`/`INSERT`/`UPDATE`/`DELETE` on required tables |
| `app_migrator` | DDL privileges required to run migrations |
| `app_readonly` | `SELECT` for restricted read/reporting tasks |
| `app_auditor` | `SELECT` on audit logs per operational permissions |
| `app_admin` | Elevated administrative privileges, used under strict controls |

Never configure a superuser or table-owner role for the application connection pool. When using PostgreSQL RLS, the runtime role must not hold `BYPASSRLS`; verify effective permissions rather than assuming from role names.

Migration jobs can use separate DDL credentials. There is no need to grant `CREATE`/`ALTER`/`DROP` to the runtime application if it does not execute schema migrations.

Load database secrets from a secret manager or deployment environment; never commit passwords to repositories or print them in startup logs.

## 20. Soft delete and access control

Soft deletes commonly add fields such as `deleted_at`, `deleted_by`, or `is_deleted`. They support recovery and history, but do not automatically protect data.

Every standard query must filter out soft-deleted rows:

~~~sql
SELECT id, title
FROM documents
WHERE tenant_id = :tenantId
  AND deleted_at IS NULL;
~~~

Decide explicitly:

- Which users may view soft-deleted records?
- Who may restore them?
- Does soft deletion emit an audit event?
- Are soft-deleted rows excluded from search and exports?
- When is data physically purged?
- Does retention apply to backups and audit logs?

Never treat `deleted_at` as a security boundary. Unauthorized users must still be denied by authorization checks even on non-deleted rows.

## 21. Audit logs and access to audit logs

Audit logs can contain sensitive details about user behavior. Permissions to read audit logs should usually be stricter than permissions to read ordinary business data.

Define clearly:

- Who is allowed to view audit events?
- Must audit log queries be scoped by tenant?
- Should actor or resource identifiers be masked?
- Who may export audit logs?
- How long are audit logs retained?
- Who can delete or modify them?
- Are accesses to the audit log itself audited?

Do not grant users access to audit logs merely because they own the business record. Viewing audit history can be gated by a dedicated permission.

When non-repudiation is required, audit events need trustworthy timestamps, authenticated actors, clear actions/resources, correlation IDs, and storage with restricted mutation rights. Avoid writing sensitive fields into before/after snapshots unless explicitly required and properly protected.

## 22. Testing auditing

Auditing must be verified through Spring Data mapping and the reactive context.

Test cases to cover:

- On insert, `createdBy` and `createdAt` are populated.
- On update, `updatedBy` and `updatedAt` are updated.
- `createdBy` and `createdAt` are not inadvertently overwritten during updates.
- When `Authentication` is absent, actor field behavior matches policy.
- Background jobs record the service/job actor.
- Timestamps are persisted and read back with the expected timezone and precision.
- Custom `EntityCallback`s do not suppress auditing callbacks.
- Bulk and native SQL paths follow explicitly defined auditing behavior.

Testing converters or callbacks in isolation does not prove Spring configuration is wired properly. Include integration tests booting the context with `@EnableR2dbcAuditing` and an R2DBC database.

For reactive security tests, inject `Authentication` into the Reactor Context on test publishers. Never assume imperative test annotations automatically propagate context into arbitrary custom publishers.

## 23. Testing row-level authorization

Seed at least two tenants or two users with isolated data:

~~~text
Tenant A
  - User A1 owns Document A1
  - User A2 owns Document A2

Tenant B
  - User B1 owns Document B1
~~~

Scenarios to verify:

| Scenario | Expected outcome |
|---|---|
| A1 reads record A1 | Allowed |
| A1 reads record A2 when owner-only read applies | Denied/hidden per API policy |
| A1 reads record B1 | Denied |
| A1 updates record B1 | Zero rows modified |
| A1 deletes record B1 | Zero rows deleted |
| Client sends tenant B while actor belongs only to tenant A | Denied |
| List/export query omits owner scope | Test catches the gap |
| Background job runs for tenant A | Affects only tenant A's data |
| Tenant context unset when RLS is active | Zero rows accessible |

Test `SELECT`, `UPDATE`, `DELETE`, counts, pagination, search, exports, and native SQL. A safe list endpoint does not guarantee the detail endpoint or bulk updates are safe.

### 23.1. Testing PostgreSQL RLS with the runtime role

When using RLS, tests must connect using a role equivalent to the runtime application role. Running tests as superuser or table owner bypasses policies and yields misleading results.

Verify:

- RLS is enabled on the intended tables.
- The runtime role cannot bypass RLS.
- Tenant context is set within the same transaction.
- Connections returned to the pool do not retain stale tenant context.
- `USING` and `WITH CHECK` policies block both unauthorized reads and unauthorized writes.
- Multiple policies do not unintentionally widen access.
- Background jobs set the right tenant context.

H2 cannot substitute for PostgreSQL RLS tests. Use Testcontainers or a real PostgreSQL test database for policy verification.

## 24. Testing sensitive data and response contracts

Write DTO and serialization tests confirming forbidden fields never appear:

- Password hashes are never returned by the API.
- Tokens and secrets never appear in responses.
- PII appears only on endpoints and for permissions that allow it.
- Masking works as specified.
- Error responses contain no SQL or bind parameters.
- Audits and logs omit forbidden sensitive values.
- Exports and file downloads enforce the same authorization rules.

Do not test only the primary JSON response. Also inspect log appenders/test sinks when anti-leakage rules apply, and verify tracing/logging configurations in integrated environments.

## 25. Common pitfalls

| Symptom | Likely cause | Fix |
|---|---|---|
| `createdBy` is always null | Auditing not enabled or missing auditor | Check `@EnableR2dbcAuditing` and `ReactiveAuditorAware` |
| `updatedBy` records wrong user | Actor read from untrusted input or wrong context | Read from verified security identity |
| Auditing works in HTTP but not in jobs | Background publisher lacks actor context | Set an explicit service/job actor |
| Entity callbacks skip native SQL | Custom SQL bypasses lifecycle mapping | Write auditing fields explicitly or use appropriate hooks |
| User swaps ID to read another row | Query lacks tenant/owner predicate | Scope every data operation |
| List is filtered but update modifies other tenant's row | `UPDATE` omits scope predicate | Add scope predicates to `UPDATE`/`DELETE` and test |
| RLS fails to block runtime queries | Role is owner/superuser/`BYPASSRLS` or policy is wrong | Verify role and policies with runtime credentials |
| Tenant A sees Tenant B's data after connection reuse | Session-level tenant variable used | Use transaction-local context on the same connection |
| Client spoofs `createdBy` | Entity bound directly from request body | Use DTOs and resolve actor from security context |
| Secrets appear in logs | Dumping full requests, entities, or exceptions | Mask/redact and restrict logged fields |
| Passwords are decryptable | Reversible encryption used instead of hashing | Use dedicated password hashing |
| Audit trail misses events after commit | Unreliable event emission outside transaction | Use a transactional outbox for atomicity |
| Runtime can alter audit logs | Runtime role granted `UPDATE`/`DELETE` | Separate append/read privileges from admin roles |
| DTO leaks internal fields | Entities returned directly | Use allowlisted response DTOs |

## 26. Implementation checklist

### Auditing

- [ ] Enable `@EnableR2dbcAuditing`.
- [ ] Declare `@CreatedBy`, `@CreatedDate`, `@LastModifiedBy`, and `@LastModifiedDate` as needed.
- [ ] Provide `ReactiveAuditorAware` when tracking actors.
- [ ] Resolve actors from server-authenticated identities.
- [ ] Never use `ThreadLocal` or `block()` inside a reactive auditor.
- [ ] Define actors for background jobs and service accounts.
- [ ] Use consistent time types and UTC timezone storage.
- [ ] Design a separate audit trail if full history is required.

### Row-level authorization

- [ ] Tenant/owner scopes originate from a verified context.
- [ ] `SELECT`, `UPDATE`, and `DELETE` all enforce scope predicates.
- [ ] Search, counts, pagination, and exports share the same policy.
- [ ] Never trust client-supplied IDs or tenant IDs.
- [ ] Schema constraints and indexes support tenant isolation.
- [ ] Evaluate PostgreSQL RLS for defense in depth.
- [ ] Runtime database role cannot bypass RLS.
- [ ] Tenant context is set transaction-locally.
- [ ] Tests verify cross-tenant and cross-owner isolation.

### Sensitive data

- [ ] Collect only fields genuinely required.
- [ ] Responses use allowlisted DTOs.
- [ ] Passwords use dedicated password hashing.
- [ ] Readable sensitive fields are encrypted with separate key management.
- [ ] TLS and encryption at rest are configured appropriately.
- [ ] Secrets are excluded from source control and logs.
- [ ] All SQL data values use bind parameters.
- [ ] Dynamic SQL identifiers use allowlists.
- [ ] Logs, traces, and metrics exclude unnecessary PII and secrets.
- [ ] Retention, purge, and backup policies are established.
- [ ] Audit log read and export permissions are restricted.

## 27. Conclusion

In Spring Data R2DBC, auditing, row-level authorization, and sensitive data protection are three distinct layers of responsibility. Spring Data auditing can automatically populate actors and timestamps using `@CreatedBy`, `@CreatedDate`, `@LastModifiedBy`, `@LastModifiedDate`, `@EnableR2dbcAuditing`, and `ReactiveAuditorAware`. In reactive applications, resolve the actor from `SecurityContext` in the Reactor Context or from a trusted job actor context.

Row-level authorization must be enforced across every data operation. Verify tenant and owner scopes in server context and apply them to `SELECT`, `UPDATE`, `DELETE`, search, and exports. PostgreSQL RLS adds valuable defense in depth, provided runtime roles, policies, and transaction-local tenant contexts are configured properly. Auditing metadata does not replace a full audit trail; when immutable history or reliable event delivery is needed, build dedicated audit and outbox mechanisms.

Sensitive data must be protected end-to-end across collection, storage, querying, serialization, logging, and retention. Combine allowlisted DTOs, password hashing, encryption or tokenization for protected values, secure key management, least-privilege database roles, and log redaction. Finally, test auditing, cross-tenant access, RLS, response masking, and audit events against a real database and driver—protections are only trustworthy when enforced server-side and verified on every access path.
