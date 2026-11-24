# The `acl_sid`, `acl_class`, `acl_object_identity`, and `acl_entry` Tables in Spring Security ACL

## 1. Why Does an ACL System Need Four Tables?

Suppose an application manages `Document` records. Document 42 is owned by Alice. Bob may only view it; members with the `ROLE_EDITOR` authority may edit it; Mallory is denied from reading it. Document 43 belongs to the same branch and may inherit part of Document 42's permissions. An ordinary `user_role` table cannot adequately express **per-record** permissions, grant/deny ordering, or parent–child ACL relationships.

**Spring Security ACL** (*Access Control List*) stores permissions per **domain object instance** across four standard tables:

1. **`acl_sid`**: permission subjects (*security identity* – specific principal or authority).
2. **`acl_class`**: types of objects having ACLs (typically the Java class name).
3. **`acl_object_identity`**: a specific instance of an object type, such as `Document#42`, along with ACL owner and inheritance info.
4. **`acl_entry`**: individual grant or deny rules (*Access Control Entry — ACE*) for a SID on an object identity.

Spring Security documents this schema in the separate **`spring-security-acl`** module; merely adding `spring-boot-starter-security` does not include the four tables or ACL data. You must initialize the schema, configure `DataSource`, `AclService`/`LookupStrategy`, and integrate `AclPermissionEvaluator` if using `hasPermission(...)` in Method Security.

This lesson focuses on the **four-table structure**, keys, constraints, how records link together, bitmasks, inheritance, diagnostic queries, and a runnable Java 17 demo using Spring Boot 3.5.6, HSQLDB, and Spring Security 6.5.x. More complex owner/tenant policies are noted where relevant, without conflating them with the default ACL schema.

### 1.1. Entity Relationship Diagram

```text
              acl_class
         (id PK, class UNIQUE)
                  │ 1
                  │
                  ▼ N
          acl_object_identity ──────┐
        (id PK, type, object ID,     │
         parent, owner, inherit)    │ self-FK parent_object
                  │ 1               │
                  ▼ N               ┘
               acl_entry
         (id PK, ace_order,
          sid FK, mask, grant)
                  │ N
                  ▼ 1
                acl_sid
     (id PK, principal flag, sid)
                  ▲
                  │ 1
                  └── owner_sid FK from acl_object_identity
```

Core tables and relationships:

| Table | What One Row Represents | Key Constraints |
|---|---|---|
| `acl_sid` | A principal or a GrantedAuthority recognized by the ACL | PK `id`; unique `(sid, principal)` |
| `acl_class` | A domain type protected by ACLs | PK `id`; unique `class` |
| `acl_object_identity` | A specific instance of a domain type | PK `id`; unique `(object_id_class, object_id_identity)`; FKs to class, owner SID, parent ACL |
| `acl_entry` | An ordered ACE for a SID and object | PK `id`; unique `(acl_object_identity, ace_order)`; FKs to object identity and SID |

**Two easily confused ID pairs:** `acl_object_identity.id` is the **internal key of the ACL row**; `acl_object_identity.object_id_identity` is the **ID of the business record**, such as 42. `acl_entry.acl_object_identity` always points to the ACL's **internal ID**, never directly to `document.id`.

## 2. `acl_sid` — Storing Recipient SIDs (Security Identities)

A SID represents a **user** or a **GrantedAuthority**. Columns:

| Column | Typical Type | Meaning |
|---|---|---|
| `id` | BIGINT, PK | Database-generated internal ID |
| `principal` | BOOLEAN NOT NULL | `TRUE`: specific principal; `FALSE`: authority |
| `sid` | VARCHAR(100) NOT NULL | Principal name or GrantedAuthority name |
| unique `(sid, principal)` | Constraint | No two SIDs share both the same name and type |

Example:

| id | principal | sid |
|---:|:---:|---|
| 1 | true | alice |
| 2 | true | bob |
| 3 | true | mallory |
| 4 | false | ROLE_EDITOR |

**`principal = true`** maps to `PrincipalSid("bob")`; **`principal = false`** maps to `GrantedAuthoritySid("ROLE_EDITOR")`. These are two distinct SID kinds even within the same system. Having both `(true, "alice")` and `(false, "alice")` is valid under the unique constraint; the application should enforce naming conventions to avoid confusion.

The `acl_sid` table **is not a user table** and does not store passwords, login credentials, or all role memberships. It only defines **identities that can receive ACEs**. Which `GrantedAuthority` instances a user holds comes from the `Authentication` built by your security provider/converter, not from implicit joins inside `acl_sid`.

When an ACE points to SID `ROLE_EDITOR`, **any valid `Authentication` containing that authority** can be evaluated against that role ACE, depending on evaluation order and permission policy. This avoids creating separate ACEs for every principal holding the role.

**Note:** SID strings typically match the identity in `Authentication`; if usernames change or `ROLE_` conventions change, plan an ACL migration. Never assume changing a display name in the UI has no impact on `acl_sid` rows.

## 3. `acl_class` — Resource Types Protected by ACLs

Columns:

| Column | Typical Type | Meaning |
|---|---|---|
| `id` | BIGINT, PK | Internal ID for the domain type |
| `class` | VARCHAR(100) UNIQUE | Java type identifier, usually the **fully qualified class name** |

Example:

```text
id=7
class=com.example.acldemo.Document
```

This identifier must **match the type used by `ObjectIdentity`**:

```java
ObjectIdentity identity =
    new ObjectIdentityImpl(Document.class, 42L);
```

This is an **illustrative API snippet**, requiring imports for `org.springframework.security.acls.domain.ObjectIdentityImpl`, `org.springframework.security.acls.model.ObjectIdentity`, and your application's `Document` class. Initializing with `Document.class` produces type `com.example.acldemo.Document`; using `ObjectIdentityImpl(String type, Serializable identifier)` uses whatever `type` string the developer specifies. If the DB stores `com.example.legacy.Document` while runtime looks up `com.example.acldemo.Document`, the ACL will not be found.

**Do not confuse `acl_class.id` with a document ID.** `acl_class` holds one row per **type**, and millions of `acl_object_identity` rows can point to that single row.

Cases requiring care:
- Refactoring package or class names affects `class` in ACLs; plan migrations before renaming domain types.
- Multiple modules defining `Document` in different packages are **two** distinct types.
- If you prefer a stable alias over a Java class name, use `ObjectIdentityImpl(String, id)` consistently from ACL creation through lookup, and verify compatibility with services/lookup strategies.
- The unique constraint on `class` prevents duplicate type rows, yet cannot guarantee code chooses the right type string.

## 4. `acl_object_identity` — The ACL "Address" of Each Record

This table binds a domain type to **a specific object** and stores inheritance metadata.

| Column | Typical Type | Meaning |
|---|---|---|
| `id` | BIGINT, PK | Internal ID of the ACL object identity |
| `object_id_class` | BIGINT NOT NULL | FK to `acl_class.id` |
| `object_id_identity` | VARCHAR(36) NOT NULL in the 6.5 sample schema | Domain object ID stored as a string |
| `parent_object` | BIGINT NULL | Self-FK to parent ACL's `acl_object_identity.id` |
| `owner_sid` | BIGINT NULL | FK to `acl_sid.id` representing the ACL owner |
| `entries_inheriting` | BOOLEAN NOT NULL | Whether inherited ACEs from the parent ACL may be consulted |
| unique `(object_id_class, object_id_identity)` | Constraint | One object of a given type has at most one object identity row |

Example:

| id | object_id_class | object_id_identity | parent_object | owner_sid | entries_inheriting |
|---:|---:|---|---:|---:|:---:|
| 10 | 7 | 42 | null | 1 | false |
| 11 | 7 | 43 | 10 | 1 | true |

According to this data:
- Internal ACL `10` represents `Document#42`.
- Internal ACL `11` represents `Document#43`.
- `parent_object=10` means `Document#43`'s ACL has `Document#42` as its parent ACL.
- `entries_inheriting=true` means parent ACEs can be consulted when deciding permissions on the child; final grant/deny depends on ACEs and the permission granting strategy.
- `owner_sid=1` points to Alice; this is the **ACL owner**, not automatically synonymous with `document.created_by` or the business owner.

### 4.1. What Permissions Does the ACL Owner Have?

**An ACL owner does not automatically have `READ` or `WRITE` on the domain record.** `Acl#getOwner()` identifies the owner of the ACL object; `AclAuthorizationStrategy` can use the owner to decide who may **modify the ACL/ACEs**. Permission to **read/edit business content** must still be modeled via ACEs or application policies unless your system deliberately introduces a different rule.

This misconception can create vulnerabilities: seeing `owner_sid=alice` and assuming every API can skip `hasPermission` for Alice. Distinguish:
1. **ACL administration**: who may edit ACE sharing settings?
2. **Business authorization**: who may read/delete/edit the document?

The two permissions are not identical.

### 4.2. ACL Inheritance and the Self-FK

`parent_object` provides the parent ACL tree/chain, while `entries_inheriting` controls whether the child ACL **consults parent ACEs**. A child with `parent_object` set yet `entries_inheriting=false` will not automatically inherit parent rights.

To avoid bugs:
- Never create cycles like `A → B → A`. A self-FK only guarantees the parent row exists; it **does not prevent cycles**.
- Never let a parent ACL cross tenant/project scopes unless business policy allows it.
- Clearly understand precedence between local ACEs and inherited ACEs; ACE ordering and permission strategy affect decisions.
- When transferring ownership or moving a document across tenants, re-evaluate `owner_sid`, `parent_object`, and inherited ACEs.

### 4.3. ID Types in the Database

The 6.5 PostgreSQL schema documentation uses `object_id_identity VARCHAR(36)`, whereas Java examples often pass `Long`. `ObjectIdentityImpl` represents internal identity with data mappable to strings for querying; however, **UUIDs, `BigInteger`, or IDs exceeding 36 characters** must be evaluated against column lengths and support in your ACL/JDBC version. Never alter column types in production without checking `JdbcAclService`'s SQL and cache identity assumptions.

Multi-tenant apps with colliding IDs between tenant A and B must ensure domain IDs are **unique within the same Java type**, or design a compatible composite identity/alias. The default unique constraint `(object_id_class, object_id_identity)` **has no `tenant_id`**: if two tenants both have `Document#42` in a shared table, two ACL object identity rows cannot share the same type and ID. Choose globally unique IDs, distinct types, or dedicated schema/identity strategies after understanding this limit.

## 5. `acl_entry` — Ordered Grant/Deny Permission Rules

Each row is an **Access Control Entry (ACE)** binding a SID to an object identity and a permission/mask.

| Column | Typical Type | Meaning |
|---|---|---|
| `id` | BIGINT, PK | Internal ID of the ACE |
| `acl_object_identity` | BIGINT NOT NULL | FK to `acl_object_identity.id` |
| `ace_order` | INTEGER NOT NULL | Position of the ACE within the object's ACL |
| `sid` | BIGINT NOT NULL | FK to `acl_sid.id` (principal/authority) |
| `mask` | INTEGER NOT NULL | Permission bitmask (e.g., 1=READ, 2=WRITE) |
| `granting` | BOOLEAN NOT NULL | `true`: allow; `false`: deny |
| `audit_success` | BOOLEAN NOT NULL | Flag requesting audit when ACE applies and succeeds |
| `audit_failure` | BOOLEAN NOT NULL | Flag requesting audit when ACE applies and fails |
| unique `(acl_object_identity, ace_order)` | Constraint | Within one ACL, ACE order values cannot collide |

Example on internal ACL `10` (Document#42):

| id | acl_object_identity | ace_order | sid | mask | granting | Meaning |
|---:|---:|---:|---:|---:|:---:|---|
| 100 | 10 | 0 | 2 (bob) | 1 | true | Bob gets READ |
| 101 | 10 | 1 | 3 (mallory) | 1 | false | Mallory is DENIED READ |
| 102 | 10 | 2 | 4 (ROLE_EDITOR) | 2 | true | Users with authority ROLE_EDITOR get WRITE |

ACL `11` (Document#43) adds:

| id | acl_object_identity | ace_order | sid | mask | granting | Meaning |
|---:|---:|---:|---:|---:|:---:|---|
| 103 | 11 | 0 | 2 (bob) | 2 | true | Bob gets direct WRITE on child |

Because Document#43's ACL has `entries_inheriting=true`, Bob can inherit READ from the parent ACL while having direct WRITE on the child. We verify this through the ACL runtime in the demo rather than concluding from a SQL JOIN alone.

### 5.1. `BasePermission` Bitmasks

Spring Security ACL uses integer bitmasks. Default permissions in `BasePermission`:

| Permission | Bit | Decimal Mask | Used For |
|---|---:|---:|---|
| `BasePermission.READ` | 0 | 1 | Read |
| `BasePermission.WRITE` | 1 | 2 | Write |
| `BasePermission.CREATE` | 2 | 4 | Create |
| `BasePermission.DELETE` | 3 | 8 | Delete |
| `BasePermission.ADMINISTRATION` | 4 | 16 | Administer ACL |

Bitmask values are **permission bits**, not roles or document IDs. For instance, `mask=3` has bit 0 and bit 1 enabled (1 OR 2); how the engine matches a multi-permission request also depends on `PermissionFactory` and `PermissionGrantingStrategy`. **Never interpret a mask directly in SQL and treat it as the final decision.** Spring Security uses `BasePermission`, `CumulativePermission`, and granting strategies to resolve according to ACL policy.

### 5.2. ACE Order Matters More Than Physical Row Position

`ace_order` is a logical position, not a PK or timestamp. When ACEs match multiple SIDs/permissions or mix allow and deny, **ACE order** can influence the result under `DefaultPermissionGrantingStrategy`. Never rely on `id` ordering, INSERT order, or an unordered query without `ORDER BY` to determine permissions.

An ACL can contain **multiple ACEs for the same SID**, provided each sits at a distinct `ace_order`; the unique constraint is `(acl_object_identity, ace_order)`, **not** `(acl_object_identity, sid, mask)`. Deduplication, deny interpretation, and combined permissions belong to policy/strategy.

### 5.3. Two Audit Flags Do Not Automatically Create an Audit Log Database

`audit_success` and `audit_failure` are **metadata** that `PermissionGrantingStrategy`/`AuditLogger` can inspect when an ACE is evaluated. They are **not** an audit log table and do not guarantee every request is durably logged. In the demo, both flags are `false`; production apps must configure loggers, retention, and sensitive-data scrubbing separately.

## 6. Reference DDL for PostgreSQL: All Four Tables and Relationships

This is **DDL adapted from the default Spring Security 6.5 schema** for PostgreSQL, not generic SQL runnable on every database. Column names must preserve the exact contract expected by the library's JDBC ACL queries. Run with a database role permitted to create schemas, using Flyway/Liquibase migrations in production.

```sql
CREATE TABLE acl_sid (
    id BIGSERIAL PRIMARY KEY,
    principal BOOLEAN NOT NULL,
    sid VARCHAR(100) NOT NULL,
    CONSTRAINT uq_acl_sid_identity UNIQUE (sid, principal)
);

CREATE TABLE acl_class (
    id BIGSERIAL PRIMARY KEY,
    class VARCHAR(100) NOT NULL,
    CONSTRAINT uq_acl_class_name UNIQUE (class)
);

CREATE TABLE acl_object_identity (
    id BIGSERIAL PRIMARY KEY,
    object_id_class BIGINT NOT NULL
        REFERENCES acl_class(id),
    object_id_identity VARCHAR(36) NOT NULL,
    parent_object BIGINT NULL
        REFERENCES acl_object_identity(id),
    owner_sid BIGINT NULL
        REFERENCES acl_sid(id),
    entries_inheriting BOOLEAN NOT NULL,
    CONSTRAINT uq_acl_object
        UNIQUE (object_id_class, object_id_identity)
);

CREATE TABLE acl_entry (
    id BIGSERIAL PRIMARY KEY,
    acl_object_identity BIGINT NOT NULL
        REFERENCES acl_object_identity(id),
    ace_order INTEGER NOT NULL,
    sid BIGINT NOT NULL
        REFERENCES acl_sid(id),
    mask INTEGER NOT NULL,
    granting BOOLEAN NOT NULL,
    audit_success BOOLEAN NOT NULL,
    audit_failure BOOLEAN NOT NULL,
    CONSTRAINT uq_acl_ace_order
        UNIQUE (acl_object_identity, ace_order)
);
```

**Meaning of the constraints:**

1. `acl_sid(sid, principal)` is unique because a principal and an authority may share the same name string yet are two distinct SIDs.
2. `acl_class(class)` is unique because each type needs only one ID.
3. `acl_object_identity(object_id_class, object_id_identity)` is unique, preventing two ACL object identities for the same object/type.
4. `acl_entry(acl_object_identity, ace_order)` is unique, preventing duplicate ACE positions within an object's ACL.
5. FKs ensure ACEs cannot point to nonexistent SIDs/objects; owner and parent may still be null.

**Deletion order warning:** To delete an ACL object identity, you must first handle its `acl_entry` rows and any child ACLs referencing `parent_object`; the default FKs above do not use `ON DELETE CASCADE`. Never delete an `acl_sid` row still referenced by ACEs or ACL owners.

### 6.1. PostgreSQL and `JdbcMutableAclService`: Identity Queries

Per official documentation, `JdbcMutableAclService` defaults its generated-ID retrieval query to **HSQLDB** (`call identity()`). On PostgreSQL, when using `JdbcMutableAclService` to insert new SIDs/classes, configure:

```java
jdbcMutableAclService.setClassIdentityQuery(
    "select currval(pg_get_serial_sequence('acl_class', 'id'))"
);
jdbcMutableAclService.setSidIdentityQuery(
    "select currval(pg_get_serial_sequence('acl_sid', 'id'))"
);
```

This is a **configuration snippet**, not a standalone class; `jdbcMutableAclService` is the registered bean instance. Do not copy these two PostgreSQL queries into the HSQLDB demo below: HSQLDB uses different identity retrieval syntax. For MySQL/MariaDB, SQL Server, Oracle, or H2, check the schema and identity query for your exact dialect/version.

### 6.2. Indexes and Operations

Unique constraints usually create indexes on the constrained keys, yet **do not automatically index every FK optimally**. Before scaling to many ACLs, inspect execution plans and consider indexes on:
- `acl_entry.sid` when filtering by recipient or auditing grants.
- `acl_object_identity.parent_object` when traversing child ACLs.
- Frequently queried FK columns.
- Business columns `tenant_id`, `owner_id` on domain tables (outside the four default tables).

Never arbitrarily alter column lengths, types, or names while using `JdbcAclService`'s default queries. Inspect the schema shipped with your exact `spring-security-acl` version and use migrations with a rollback plan.

## 7. SQL Queries to Inspect All Four Tables Together

These are **diagnostic and audit queries**, not a replacement for `Acl#isGranted`. SQL joins do not implement full ACE ordering, inheritance, SID hierarchies, or deny logic.

### 7.1. Finding the ACL Object Identity of Document#42

```sql
SELECT
    o.id AS acl_pk,
    c.class AS domain_type,
    o.object_id_identity AS domain_id,
    o.parent_object,
    o.entries_inheriting,
    s.sid AS acl_owner
FROM acl_object_identity o
JOIN acl_class c ON c.id = o.object_id_class
LEFT JOIN acl_sid s ON s.id = o.owner_sid
WHERE c.class = 'com.example.acldemo.Document'
  AND o.object_id_identity = '42';
```

**Reading the result:** `acl_pk` is the internal ID of the object's ACL; `domain_id` is the business database ID; `acl_owner` is the ACL owner's SID, not a READ ACE.

### 7.2. Listing ACEs in Order for an Object

```sql
SELECT
    e.ace_order,
    s.principal,
    s.sid,
    e.mask,
    e.granting,
    e.audit_success,
    e.audit_failure
FROM acl_entry e
JOIN acl_object_identity o
    ON o.id = e.acl_object_identity
JOIN acl_class c ON c.id = o.object_id_class
JOIN acl_sid s ON s.id = e.sid
WHERE c.class = 'com.example.acldemo.Document'
  AND o.object_id_identity = '42'
ORDER BY e.ace_order;
```

With the demo seed rows, the logical output is: Bob READ=1 grant; Mallory READ=1 deny; ROLE_EDITOR WRITE=2 grant, ordered by `ace_order` 0, 1, 2. SQL only displays raw rows, without Authentication authority SIDs or inheritance.

### 7.3. Finding Direct READ-Granting ACEs for a Principal

```sql
SELECT
    c.class,
    o.object_id_identity,
    s.sid,
    e.ace_order,
    e.mask
FROM acl_entry e
JOIN acl_sid s ON s.id = e.sid
JOIN acl_object_identity o
    ON o.id = e.acl_object_identity
JOIN acl_class c ON c.id = o.object_id_class
WHERE s.principal = TRUE
  AND s.sid = 'bob'
  AND e.granting = TRUE
  AND (e.mask & 1) = 1
ORDER BY c.class, o.object_id_identity;
```

**Strictly for direct reporting.** It can miss inherited READs or authority-based READs, and does not apply full deny/ACE precedence. Never use this query as "all documents Bob can read" in a production API; use properly scoped ACL queries or tested `AclService`/policies.

## 8. Runnable Java 17 Example: Spring Security ACL + HSQLDB

To see the four tables actually read by the library, let us build an app with no HTTP endpoints using Spring Boot **3.5.6**, Java 17, Spring Security **6.5.x managed by Boot**, `spring-security-acl`, Spring JDBC, HSQLDB, and JUnit 5.

**Why choose HSQLDB?** Spring Security's JDBC ACL module ships an HSQLDB schema and default identity queries tailored to this dialect. The demo DDL is formatted for readability while keeping the exact columns/constraints of the 6.5 ACL schema. Never apply this DDL verbatim to PostgreSQL: section 6 provides the PostgreSQL variant.

**Limits:** This is an ACL and SQL schema integration test. There is no real `document` business table, no real username/password login, and no JWT/tenant policy. Stub methods return strings to demonstrate authorization.

### 8.1. Directory Layout

```text
acl-four-tables-demo/
  pom.xml
  src/main/java/com/example/acldemo/
    AclTablesApplication.java
    Document.java
    AclSecurityConfig.java
    DocumentService.java
  src/main/resources/
    schema.sql
    data.sql
  src/test/java/com/example/acldemo/
    AclIntegrationTest.java
```

### 8.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>acl-four-tables-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-acl</artifactId>
        </dependency>
        <dependency>
            <groupId>org.hsqldb</groupId>
            <artifactId>hsqldb</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 8.3. `schema.sql` — HSQLDB, All Four Tables

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE acl_sid (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 1000) PRIMARY KEY,
    principal BOOLEAN NOT NULL,
    sid VARCHAR_IGNORECASE(100) NOT NULL,
    CONSTRAINT uq_sid UNIQUE (sid, principal)
);

CREATE TABLE acl_class (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 1000) PRIMARY KEY,
    class VARCHAR_IGNORECASE(100) NOT NULL,
    CONSTRAINT uq_class UNIQUE (class)
);

CREATE TABLE acl_object_identity (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 1000) PRIMARY KEY,
    object_id_class BIGINT NOT NULL,
    object_id_identity VARCHAR_IGNORECASE(36) NOT NULL,
    parent_object BIGINT,
    owner_sid BIGINT,
    entries_inheriting BOOLEAN NOT NULL,
    CONSTRAINT uq_object_type_id
        UNIQUE (object_id_class, object_id_identity),
    CONSTRAINT fk_object_class
        FOREIGN KEY (object_id_class) REFERENCES acl_class(id),
    CONSTRAINT fk_object_parent
        FOREIGN KEY (parent_object) REFERENCES acl_object_identity(id),
    CONSTRAINT fk_object_owner
        FOREIGN KEY (owner_sid) REFERENCES acl_sid(id)
);

CREATE TABLE acl_entry (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 1000) PRIMARY KEY,
    acl_object_identity BIGINT NOT NULL,
    ace_order INTEGER NOT NULL,
    sid BIGINT NOT NULL,
    mask INTEGER NOT NULL,
    granting BOOLEAN NOT NULL,
    audit_success BOOLEAN NOT NULL,
    audit_failure BOOLEAN NOT NULL,
    CONSTRAINT uq_entry_order
        UNIQUE (acl_object_identity, ace_order),
    CONSTRAINT fk_entry_object
        FOREIGN KEY (acl_object_identity) REFERENCES acl_object_identity(id),
    CONSTRAINT fk_entry_sid
        FOREIGN KEY (sid) REFERENCES acl_sid(id)
);
```

Because `GENERATED BY DEFAULT AS IDENTITY` is used, the seed file below can assign fixed IDs below 1000 for readable tests; new DB-generated IDs start at 1000. While constraint names and identity start values differ from the official HSQLDB schema doc, all **column names and relationships** follow the ACL contract. In real apps, use the exact schema shipped with your library version and manage changes via migrations rather than casually altering default SQL.

### 8.4. `data.sql` — A Transparent Example with Parent ACL

**`src/main/resources/data.sql`**

```sql
INSERT INTO acl_sid(id, principal, sid)
VALUES (1, TRUE, 'alice');
INSERT INTO acl_sid(id, principal, sid)
VALUES (2, TRUE, 'bob');
INSERT INTO acl_sid(id, principal, sid)
VALUES (3, TRUE, 'mallory');
INSERT INTO acl_sid(id, principal, sid)
VALUES (4, FALSE, 'ROLE_EDITOR');

INSERT INTO acl_class(id, class)
VALUES (7, 'com.example.acldemo.Document');

INSERT INTO acl_object_identity(
    id, object_id_class, object_id_identity,
    parent_object, owner_sid, entries_inheriting
) VALUES (
    10, 7, '42', NULL, 1, FALSE
);

INSERT INTO acl_object_identity(
    id, object_id_class, object_id_identity,
    parent_object, owner_sid, entries_inheriting
) VALUES (
    11, 7, '43', 10, 1, TRUE
);

INSERT INTO acl_entry(
    id, acl_object_identity, ace_order, sid,
    mask, granting, audit_success, audit_failure
) VALUES (100, 10, 0, 2, 1, TRUE, FALSE, FALSE);

INSERT INTO acl_entry(
    id, acl_object_identity, ace_order, sid,
    mask, granting, audit_success, audit_failure
) VALUES (101, 10, 1, 3, 1, FALSE, FALSE, FALSE);

INSERT INTO acl_entry(
    id, acl_object_identity, ace_order, sid,
    mask, granting, audit_success, audit_failure
) VALUES (102, 10, 2, 4, 2, TRUE, FALSE, FALSE);

INSERT INTO acl_entry(
    id, acl_object_identity, ace_order, sid,
    mask, granting, audit_success, audit_failure
) VALUES (103, 11, 0, 2, 2, TRUE, FALSE, FALSE);
```

From `data.sql`:
- `acl_sid.id=2` is Bob, `principal=true`.
- `acl_sid.id=4` is authority `ROLE_EDITOR`, `principal=false`.
- `acl_class.id=7` is Java type `com.example.acldemo.Document`.
- `acl_object_identity.id=10` represents domain ID `42`, owner SID Alice.
- `acl_object_identity.id=11` represents domain ID `43`, parent ACL 10 with inheritance enabled.
- ACE 100 grants READ=1 to Bob on 42.
- ACE 101 denies READ=1 to Mallory on 42.
- ACE 102 grants WRITE=2 to ROLE_EDITOR on 42.
- ACE 103 grants direct WRITE=2 to Bob on 43.

**Seed insertion order:** insert SIDs + classes first, parent object identities before children, then ACEs. Reversing this order violates FKs—which is precisely the benefit of relational constraints.

### 8.5. Spring Boot and Domain Object

**`src/main/java/com/example/acldemo/AclTablesApplication.java`**

```java
package com.example.acldemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AclTablesApplication {
    public static void main(String[] args) {
        SpringApplication.run(AclTablesApplication.class, args);
    }
}
```

**`src/main/java/com/example/acldemo/Document.java`**

```java
package com.example.acldemo;

public record Document(Long id, String title) {
    // ObjectIdentityImpl(Object) locates public getId() via reflection.
    public Long getId() {
        return id;
    }
}
```

The package name **must match** `acl_class.class` in `data.sql`. If you move it to `com.example.other` without updating the ACL seed, lookups will fail.

### 8.6. Real Spring Security ACL Configuration

**`src/main/java/com/example/acldemo/AclSecurityConfig.java`**

```java
package com.example.acldemo;

import javax.sql.DataSource;

import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.acls.AclPermissionEvaluator;
import org.springframework.security.acls.domain.AclAuthorizationStrategy;
import org.springframework.security.acls.domain.AclAuthorizationStrategyImpl;
import org.springframework.security.acls.domain.ConsoleAuditLogger;
import org.springframework.security.acls.domain.DefaultPermissionGrantingStrategy;
import org.springframework.security.acls.domain.SpringCacheBasedAclCache;
import org.springframework.security.acls.jdbc.BasicLookupStrategy;
import org.springframework.security.acls.jdbc.JdbcMutableAclService;
import org.springframework.security.acls.jdbc.LookupStrategy;
import org.springframework.security.acls.model.AclCache;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.acls.model.PermissionGrantingStrategy;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

@Configuration
@EnableMethodSecurity
public class AclSecurityConfig {

    @Bean
    static MethodSecurityExpressionHandler expressionHandler(
            AclPermissionEvaluator evaluator) {
        DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }

    @Bean
    static AclPermissionEvaluator aclPermissionEvaluator(AclService service) {
        return new AclPermissionEvaluator(service);
    }

    @Bean
    static JdbcMutableAclService aclService(
            DataSource dataSource,
            LookupStrategy lookupStrategy,
            AclCache aclCache) {
        return new JdbcMutableAclService(
            dataSource, lookupStrategy, aclCache
        );
    }

    @Bean
    static LookupStrategy lookupStrategy(
            DataSource dataSource,
            AclCache aclCache,
            AclAuthorizationStrategy aclAuthorizationStrategy,
            PermissionGrantingStrategy permissionGrantingStrategy) {
        return new BasicLookupStrategy(
            dataSource, aclCache,
            aclAuthorizationStrategy, permissionGrantingStrategy
        );
    }

    @Bean
    static AclCache aclCache(
            PermissionGrantingStrategy permissionGrantingStrategy,
            AclAuthorizationStrategy aclAuthorizationStrategy) {
        return new SpringCacheBasedAclCache(
            new ConcurrentMapCache("aclCache"),
            permissionGrantingStrategy,
            aclAuthorizationStrategy
        );
    }

    @Bean
    static AclAuthorizationStrategy aclAuthorizationStrategy() {
        return new AclAuthorizationStrategyImpl(
            new SimpleGrantedAuthority("ROLE_ACL_ADMIN")
        );
    }

    @Bean
    static PermissionGrantingStrategy permissionGrantingStrategy() {
        return new DefaultPermissionGrantingStrategy(
            new ConsoleAuditLogger()
        );
    }
}
```

Components in the configuration:

| Component | Responsibility |
|---|---|
| `AclPermissionEvaluator` | Translates `hasPermission(...)` queries into ACL checks |
| `DefaultMethodSecurityExpressionHandler` | Supplies the evaluator to SpEL expressions in Method Security |
| `JdbcMutableAclService` | Reads ACLs and creates/updates ACLs in the DB |
| `BasicLookupStrategy` | Fetches ACLs/ACEs by object identity with batched query optimization |
| `SpringCacheBasedAclCache` | Caches ACLs via Spring Cache |
| `AclAuthorizationStrategyImpl` | Controls **who may edit ACL metadata/ACEs**, distinct from business WRITE |
| `DefaultPermissionGrantingStrategy` | Evaluates ACE order, SIDs, and permission masks |
| `ConsoleAuditLogger` | Illustrative audit logger; does not create an audit log table |

**Important note:** `@EnableMethodSecurity` activates the `@PreAuthorize`/`@PostAuthorize` interceptor; having ACL service beans without enabling Method Security leaves annotations unenforced. This setup follows the 6.5 pattern; in real apps, swap in production cache/audit loggers and handle eviction when ACEs change.

### 8.7. Service Using ID and Object Forms

**`src/main/java/com/example/acldemo/DocumentService.java`**

```java
package com.example.acldemo;

import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    @PreAuthorize(
        "hasPermission(#id, 'com.example.acldemo.Document', " +
        "T(org.springframework.security.acls.domain.BasePermission).READ)"
    )
    public String read(@P("id") Long id) {
        return "read:" + id;
    }

    @PreAuthorize(
        "hasPermission(#id, 'com.example.acldemo.Document', " +
        "T(org.springframework.security.acls.domain.BasePermission).WRITE)"
    )
    public String write(@P("id") Long id) {
        return "write:" + id;
    }

    @PostAuthorize(
        "hasPermission(returnObject, " +
        "T(org.springframework.security.acls.domain.BasePermission).READ)"
    )
    public Document load(@P("id") Long id) {
        return new Document(id, "sample");
    }
}
```

`read`/`write` use `#id`, the **exact Java class name**, and `BasePermission.READ`/`WRITE`. `@P("id")` guarantees the parameter variable resolves reliably even if parameter names are omitted at compile time.

`load` demonstrates post-invocation checking by object: `ObjectIdentityImpl(Object)` extracts the ID from `Document`'s `getId()`. Because `load` only constructs a demo object (no DB writes or network calls), it is safe for demonstrating post-checks. **Never rely on `@PostAuthorize` as the sole guard on mutations with side effects.**

In real code, `write` must add record updates, tenant scoping, transactions, and optimistic locking; this demo only verifies the ACL decision.

### 8.8. JUnit Integration Tests — Checking Four Tables and Decisions

**`src/test/java/com/example/acldemo/AclIntegrationTest.java`**

```java
package com.example.acldemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class AclIntegrationTest {
    @Autowired DocumentService service;
    @Autowired JdbcTemplate jdbc;

    private int count(String table) {
        Integer total = jdbc.queryForObject(
            "SELECT COUNT(*) FROM " + table, Integer.class
        );
        return total.intValue();
    }

    @Test
    void fourTablesContainExpectedRows() {
        assertEquals(4, count("acl_sid"));
        assertEquals(1, count("acl_class"));
        assertEquals(2, count("acl_object_identity"));
        assertEquals(4, count("acl_entry"));
    }

    @Test
    void principalAndAuthoritySidAreDifferentKinds() {
        Boolean bobIsPrincipal = jdbc.queryForObject(
            "SELECT principal FROM acl_sid WHERE sid = ?",
            Boolean.class, "bob"
        );
        Boolean editorIsPrincipal = jdbc.queryForObject(
            "SELECT principal FROM acl_sid WHERE sid = ?",
            Boolean.class, "ROLE_EDITOR"
        );
        assertTrue(bobIsPrincipal);
        assertFalse(editorIsPrincipal);
    }

    @Test
    void identityRelatesClassToDomainId() {
        String type = jdbc.queryForObject(
            """
            SELECT c.class
            FROM acl_object_identity o
            JOIN acl_class c ON c.id = o.object_id_class
            WHERE o.object_id_identity = ?
            """,
            String.class, "42"
        );
        assertEquals("com.example.acldemo.Document", type);
    }

    @Test
    void childHasParentAndInheritanceEnabled() {
        Long parent = jdbc.queryForObject(
            "SELECT parent_object FROM acl_object_identity WHERE id = 11",
            Long.class
        );
        Boolean enabled = jdbc.queryForObject(
            "SELECT entries_inheriting FROM acl_object_identity WHERE id = 11",
            Boolean.class
        );
        assertEquals(10L, parent);
        assertTrue(enabled);
    }

    @Test
    void duplicateAceOrderViolatesUniqueConstraint() {
        assertThrows(DataIntegrityViolationException.class, () ->
            jdbc.update(
                """
                INSERT INTO acl_entry(
                    acl_object_identity, ace_order, sid,
                    mask, granting, audit_success, audit_failure
                ) VALUES (10, 0, 2, 1, TRUE, FALSE, FALSE)
                """
            )
        );
    }

    @Test
    @WithMockUser(username = "bob")
    void bobCanReadDocument42() {
        assertEquals("read:42", service.read(42L));
    }

    @Test
    @WithMockUser(username = "bob")
    void bobCannotWriteDocument42() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.write(42L)
        );
    }

    @Test
    @WithMockUser(username = "mallory")
    void explicitReadDenyRejectsMallory() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.read(42L)
        );
    }

    @Test
    @WithMockUser(username = "carol", roles = "EDITOR")
    void authoritySidGrantsWriteToEditor() {
        assertEquals("write:42", service.write(42L));
    }

    @Test
    @WithMockUser(username = "carol", roles = "EDITOR")
    void roleEditorDoesNotAutomaticallyGrantRead() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.read(42L)
        );
    }

    @Test
    @WithMockUser(username = "bob")
    void bobInheritsReadFromParentAcl() {
        assertEquals("read:43", service.read(43L));
    }

    @Test
    @WithMockUser(username = "bob")
    void bobHasDirectWriteOnChildAcl() {
        assertEquals("write:43", service.write(43L));
    }

    @Test
    @WithMockUser(username = "alice")
    void aclOwnerWithoutReadAceIsNotAutomaticallyAllowed() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.read(42L)
        );
    }

    @Test
    @WithMockUser(username = "bob")
    void objectBasedPostAuthorizeReadsIdFromGetId() {
        assertEquals(42L, service.load(42L).getId());
    }

    @Test
    @WithMockUser(username = "mallory")
    void objectBasedPostAuthorizeRejectsRead() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.load(42L)
        );
    }
}
```

**Why are these tests meaningful?**
- `fourTablesContainExpectedRows` verifies seed row counts: 4 SIDs, 1 class, 2 object identities, 4 ACEs.
- `principalAndAuthoritySidAreDifferentKinds` distinguishes user Bob from authority `ROLE_EDITOR`.
- `identityRelatesClassToDomainId` checks class + object ID linking without confusing ACL PK 10 with domain ID 42.
- `childHasParentAndInheritanceEnabled` verifies parent pointer and inheritance flag.
- `duplicateAceOrderViolatesUniqueConstraint` proves the DB protects ACE ordering within the same ACL.
- `@WithMockUser` tests invoke the **Spring-managed service proxy** and `AclPermissionEvaluator`, rather than computing rights via SQL JOINs.
- `@WithMockUser(username="carol",roles="EDITOR")` generates `GrantedAuthority("ROLE_EDITOR")`, verifying authority SIDs (`principal=false`).
- Alice's test shows the ACL owner **does not automatically get READ** on the record; ACL ownership plays a separate role in ACL editing.
- `@PostAuthorize` inspects the object after the target returns; here there are no side effects, so the example is safe.

**Expected result per sample configuration:** 15 tests pass; 0 failures/errors. This is the **expected outcome by design**, not recorded Maven execution output. If tests fail due to dialect, identity mapping, or dependency versions, inspect the root cause in `JdbcAclService`/`BasicLookupStrategy`, compare the schema against the DDL shipped for your exact ACL version, and never "fix" it by disabling Method Security.

Run from the directory containing `pom.xml`:

```bash
mvn test
```

Or boot the app without HTTP endpoints:

```bash
mvn spring-boot:run
```

**Testing note:** The test class intentionally omits `@Transactional` to avoid obscuring data visibility. HSQLDB initializes via `schema.sql`/`data.sql` on the embedded datasource. The duplicate ACE test expects the DB to reject the statement; original seed rows remain untouched.

## 9. Creating ACLs and Adding ACEs Properly via API (Integration Pattern)

A real application should not manipulate ACL tables directly everywhere. The library provides `MutableAclService`/`JdbcMutableAclService` to create and update object identities, ACEs, and caches. Below is an operation **inside a Spring-managed service/transaction**, after authentication and proper admin authorization checks:

```java
ObjectIdentity identity = new ObjectIdentityImpl(
    Document.class, 99L
);

// Read ACL if present; or create a new ACL for domain object 99.
MutableAcl acl;
try {
    acl = (MutableAcl) mutableAclService.readAclById(identity);
} catch (NotFoundException ex) {
    acl = mutableAclService.createAcl(identity);
}

// Grant READ to bob via PrincipalSid.
// ACE is appended at the end of the list; order will be stored in ace_order.
Sid bob = new PrincipalSid("bob");
acl.insertAce(
    acl.getEntries().size(),
    BasePermission.READ,
    bob,
    true
);
mutableAclService.updateAcl(acl);
```

This is an **integration snippet** (not a standalone Java method): it requires imports from `org.springframework.security.acls.domain`/`model` and an injected `mutableAclService`, plus configured DB schema, ACL cache, and transactions. When `createAcl` inserts a new row, the library retrieves the DB-generated identity. On PostgreSQL, configure `classIdentityQuery`/`sidIdentityQuery` as shown in section 6.1.

**Important:** Spring Security ACL does not automatically create an ACL when a repository saves an entity or delete the ACL when an entity is deleted. The application must coordinate domain record lifecycles with ACL lifecycles **deliberately**:

1. When creating a domain record, persist the record and initialize its ACL/owner/ACEs per policy.
2. When sharing, insert an ACE for the recipient SID/role and update the ACL; validate who can grant and tenant scope.
3. When revoking, delete or update the ACE in the list, update the ACL, and invalidate caches.
4. When deleting a domain record, clean up ACEs, object ACLs, and parent links to avoid orphaned ACLs.
5. Audit who changed ACEs, before/after state, reason, and timestamp, beyond `audit_success`/`audit_failure` flags.

Never expose ACL editing via an API just because a user has READ/WRITE on the business resource. `AclAuthorizationStrategy` governs ACL administration rights, distinct from `BasePermission.WRITE`.

## 10. How the Four Tables Participate in a Read Decision

Suppose user Bob calls:

```java
@PreAuthorize(
    "hasPermission(#id, 'com.example.acldemo.Document', " +
    "T(org.springframework.security.acls.domain.BasePermission).READ)"
)
public String read(@P("id") Long id) {
    return "read:" + id;
}
```

For `id=42`, the conceptual flow:

```text
1) Current Authentication: bob, authorities [...]
                  ↓
2) AclPermissionEvaluator receives (42, Document, READ)
                  ↓
3) ObjectIdentity = (com.example.acldemo.Document, 42)
                  ↓
4) acl_class: locate type row
   acl_object_identity: locate internal ACL 10
                  ↓
5) acl_sid: locate SIDs matching bob and current authorities
   acl_entry: read ACEs in order for ACL 10
                  ↓
6) PermissionGrantingStrategy:
   bob ACE mask=1, granting=true
                  ↓
7) Allow decision; Spring AOP runs the target method
```

For `Document#43`, `BasicLookupStrategy` loads the child ACL and can query the parent thanks to `parent_object` and `entries_inheriting`. If no matching child ACE exists and inheritance is enabled, the engine inspects parent ACEs per implementation/strategy. If a matching `granting=false` ACE is hit, access can be denied. Always **test both deny and inheritance**, rather than merely checking "does SQL have any grant row?".

## 11. Common Mistakes When Implementing the Four Tables

| Mistake | Why It Is Dangerous or Wrong | How to Handle |
|---|---|---|
| Treating `acl_sid` as a user/password table | SIDs do not store authentication credentials | Use an Authentication provider/IAM; keep SIDs strictly for ACLs |
| Treating `principal=false` as "no permission" | `false` means the SID represents an authority | Use `PrincipalSid` or `GrantedAuthoritySid` accurately |
| Using `object_id_identity` instead of `acl_object_identity.id` when inserting ACEs | FK points to wrong ID or fails | Use the internal ACL PK |
| Storing `acl_class.class = "Document"` while runtime uses FQCN | ACL lookup misses type match | Align `ObjectIdentity` and DB type names |
| Colliding `(class, domain ID)` across tenants | Unique constraint conflicts | Use global IDs or tenant-aware object identity strategy |
| Treating `owner_sid` as read access on all documents | ACL owner does not automatically get business READ | Separate ACL administration from content permissions |
| Assuming `parent_object` means automatic inheritance | Requires `entries_inheriting=true` | Test parent/child grant/deny |
| Creating ACL parent cycles | Self-FK does not prevent cycles | Validate acyclicity and test tree invariants |
| Ignoring `ace_order` in custom logic | Breaks grant/deny precedence | Use `Acl#isGranted` and an appropriate strategy |
| Treating `mask=3` as "all permissions" | Mask only sets READ/WRITE bits | Explicitly define `BasePermission` and custom masks |
| Using SQL JOINs instead of the ACL engine | Misses role SIDs, denies, inheritance, ordering | Use `AclService`/`AclPermissionEvaluator` |
| Forgetting `spring-security-acl` dependency | Missing ACL classes and schema | Add the version-matched module |
| Running PostgreSQL schema verbatim on HSQLDB | Wrong identity/DDL dialect | Pick dialect-compatible schema and identity queries |
| Forgetting to create/delete ACLs with entities | Orphaned ACLs or ACL-less entities | Manage lifecycle transactionally |
| Editing ACEs directly without clearing cache | Stale decisions persist | Use `MutableAclService`/cache eviction and test revocation |
| Putting `@PostAuthorize` with `hasPermission` on write methods | Side effects occur before the check | Prefer `@PreAuthorize` whenever IDs are available |
| Huge ACLs causing N+1 queries | High latency and broken pagination | Use batch lookup, caching, and early filtering |
| Assuming ACLs enforce tenancy automatically | The four default tables have no `tenant_id` | Enforce tenant boundaries in policies/queries |

### 11.1. Caching, Performance, and Consistency

`JdbcAclService` typically uses a `LookupStrategy` with batched retrieval; `SpringCacheBasedAclCache` caches ACLs to reduce queries. Whenever modifying ACEs/parents/owners, **cache invalidation** is mandatory to prevent revoked rights from remaining accepted. Across multiple app instances, an in-JVM cache does not synchronize automatically with peer nodes. You need distributed invalidation events, a shared cache, or explicit TTLs aligned with risk tolerance.

Per-object ACLs can accumulate many rows: one `acl_object_identity` per domain object plus multiple ACEs. The number of permission bits does not cap the number of objects; it only caps bit-encoded permission types. For large lists/lookups, fetching ACLs row-by-row is inefficient; use batch lookups, permission-filtered queries, or appropriate data strategies.

### 11.2. Transactions and Tenant Scoping

The ACL schema does not replace transactions. Creating an entity followed by creating its ACL needs an atomicity strategy: if the entity succeeds while ACL creation fails, the object can become inaccessible; if the entity is deleted while its ACL remains, orphaned ACLs cause confusion. Within the same DB, combine operations in one transaction where possible and define rollback/cleanup policies.

The four tables lack a `tenant_id` column by default. If a user in tenant A holds `ROLE_EDITOR`, a `ROLE_EDITOR` ACE on a tenant B object **could** match unless additional scope checks exist. Multi-tenant models must therefore tenant-scope SIDs, enforce safe object identity lookups, or add a membership/tenant guard before `AclPermissionEvaluator`.

### 11.3. Type Mismatches, Renames, and UUIDs

If `Document` is refactored to `KnowledgeDocument`, legacy `acl_class.class` values no longer match `ObjectIdentityImpl(KnowledgeDocument.class, id)`. When migrating from `Long` to UUIDs or long string IDs, verify `ObjectIdentity` compatibility, `object_id_identity` column size, and lookup strategy before migrating. Test `readAclById` using the exact class and ID used at runtime to avoid "schema has rows yet everyone gets 403."

## 12. Verification Checklist for a Deployed ACL Schema

- [ ] Exactly the four module-required ACL tables exist: `acl_sid`, `acl_class`, `acl_object_identity`, `acl_entry`.
- [ ] PKs and auto-generated IDs match the database dialect.
- [ ] Unique constraints exist on `(sid, principal)`, `(class)`, `(object_id_class, object_id_identity)`, and `(acl_object_identity, ace_order)`.
- [ ] FKs link object identity to class, owner SID, and parent object; and ACEs to object and recipient SID.
- [ ] `acl_object_identity.id` (ACL PK) is clearly distinguished from `object_id_identity` (domain ID).
- [ ] `principal=true/false` is understood as principal vs authority, never allow vs deny.
- [ ] `granting=true/false` on `acl_entry` defines an ACE's grant vs deny.
- [ ] Masks `1/2/4/8/16` follow `BasePermission`; custom masks are documented and tested.
- [ ] `ace_order` and `entries_inheriting` are evaluated via the ACL engine, never raw SQL joins claiming allow.
- [ ] `acl_class.class` matches runtime `ObjectIdentity` types.
- [ ] Schema fits PostgreSQL/HSQLDB/MySQL/SQL Server/Oracle in use; `JdbcMutableAclService` identity queries match the dialect.
- [ ] `AclService`, `LookupStrategy`, `AclCache`, `PermissionGrantingStrategy`, `AclPermissionEvaluator`, and `MethodSecurityExpressionHandler` are configured when Method Security is used.
- [ ] Seeds/tests verify principal SID vs authority SID, grant vs deny, parent–child inheritance, unique/FK constraints, and missing ACLs.
- [ ] Granting/revoking ACEs uses transactions and cache eviction; never mutate ACLs via direct DB edits without invalidation.
- [ ] Real business owner/tenant policies exist; ACL owner is never abused as an arbitrary "superuser."
- [ ] Fail-closed behavior is tested when ACLs are missing, class/ID mismatches occur, DB policy errors happen, or memberships are absent.

## 13. Official Sources for Reference

- [Spring Security 6.5 — Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html): four tables, SIDs, ACEs, `AclService`, `MutableAclService`, lookup strategies, and `AclPermissionEvaluator` setup.
- [Spring Security 6.5 — Security Database Schema](https://docs.spring.io/spring-security/reference/6.5/servlet/appendix/database-schema.html): DDL for HSQLDB, PostgreSQL, MySQL/MariaDB, SQL Server, and Oracle plus identity query notes.
- [Spring Security 6.5 — JdbcMutableAclService API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/jdbc/JdbcMutableAclService.html): creating/updating ACLs via JDBC and identity queries.
- [Spring Security 6.5 — AclPermissionEvaluator API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/AclPermissionEvaluator.html): permissions on domain objects or ID + type.
- [Spring Security 6.5 — ObjectIdentityImpl API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/domain/ObjectIdentityImpl.html): type + identifier concepts and extracting IDs from domain objects.
- [Spring Security 6.5 — Acl API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/model/Acl.html): owner, parent, entries, `isGranted(...)`, and inheritance.

**Key takeaway:** `acl_sid` answers **"who / which authority group?"**; `acl_class` answers **"which resource type?"**; `acl_object_identity` answers **"which specific record, which ACL owner, and whether inheritance is enabled?"**; `acl_entry` answers **"which SID is granted or denied which permission, and in what order?"**. The four tables provide the ACL data structure, while final decisions belong to `AclService`/`PermissionGrantingStrategy` and the application's security policies.