# Separating Administrative, Migration, Replication, and Application Roles in PostgreSQL

A very common privilege-configuration flaw is **sharing a single PostgreSQL login across cluster administration, schema migrations, replication, and application traffic**. At first, this seems convenient: there are no `permission denied` errors and only one credential set to manage. Yet if an HTTP API suffers SQL injection or credentials leak, an attacker gains power to alter schemas, read other tenants' data, drop tables, or tap into replication streams that normal application services have no business touching.

PostgreSQL enables clean separation of duties through **roles**, **ownership**, **GRANT/REVOKE**, **role membership**, **Row-Level Security (RLS)**, and specialized role attributes. A practical architecture typically distinguishes:

- **Admin / break-glass**: cluster-wide administration, reserved strictly for controlled emergency or bootstrap use.
- **Migration / deployment**: alters schemas, indexes, functions, and grants through controlled release pipelines.
- **Object owner**: a `NOLOGIN` role owning application database objects.
- **Application runtime**: reads/writes strictly the tables, columns, views, or functions required by that service.
- **Physical replication**: connects over the replication protocol to stream WAL / base backups within intended bounds.
- **Logical replication**: connects to publications/subscriptions and reads only configured published tables.
- **Backup / monitoring**: tool- and purpose-specific roles, separate from application credentials.

Architectural view:

```text
                        PostgreSQL cluster
                              |
       +----------------------+----------------------+
       |                      |                      |
  Cluster admin           Deploy pipeline       Replication/backup
  (break-glass)           (migration_login)     (repl_login)
       |                      |                      |
  Special ops only        SET ROLE app_owner    WAL / publication
                              |
                      app_owner (NOLOGIN)
                              |
                   creates/owns schemas & tables
                              |
                +-------------+---------------+
                |                             |
        Runtime read rights           Runtime write rights
        app_read (NOLOGIN)            app_write (NOLOGIN)
                |                             |
        catalog_api_login             inventory_worker_login
                |                             |
        SELECT views/columns          column UPDATE, narrow INSERT
```

Core insight: **what a database user is allowed to do must be governed by its operational duty**, never by "belonging to the same app" or "working on the same engineering team".

This lesson belongs to the **Database Engine Relational PostgreSQL** module, **Security** chapter, covering **"Separating Administrative, Migration, Replication, and Application Roles"**. We will design a role model, step through realistic SQL grants, examine physical vs. logical replication boundaries, run a reproducible lab, and establish pre-production permission tests.

---

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why roles must be separated by duty and describe the **blast radius** of credential compromise.
2. Distinguish `role`, `login role`, `group role`, `owner`, `membership`, and object privileges.
3. Design a permission matrix for admin, migration, owner, app read/write, physical replication, logical replication, backup, and monitoring roles.
4. Understand critical role attributes: `SUPERUSER`, `CREATEROLE`, `CREATEDB`, `REPLICATION`, `BYPASSRLS`, `LOGIN`, and `INHERIT`.
5. Explain why **owner roles should normally be `NOLOGIN`** and never sit inside application connection pools.
6. Use `SET ROLE` to run migrations under the owner identity via granted membership, while blocking runtime accounts from switching into the owner.
7. Grant schema `USAGE` alongside table/column-scoped `SELECT`, `INSERT`, `UPDATE`, and `DELETE`.
8. Recognize how inheritance, `PUBLIC`, and `GRANT OPTION` can expand rights unintentionally.
9. Use `ALTER DEFAULT PRIVILEGES` while distinguishing existing objects from newly created objects.
10. Understand why sequences, functions, and views require separate privilege considerations beyond tables.
11. Understand how physical replication consumes WAL and requires a different privilege and authentication surface from app SQL.
12. Distinguish logical publication/subscription privileges and initial table synchronization requirements.
13. Understand how replication slots retain WAL, creating disk and availability risks.
14. Configure separate `pg_hba.conf`, TLS, and network allowlists for replication versus application traffic.
15. Separate the `REPLICATION` attribute from publication/subscription ownership rights instead of conflating them.
16. Analyze interactions among RLS, table-owner bypass, `FORCE ROW LEVEL SECURITY`, and `BYPASSRLS` across roles.
17. Spot risks when runtime roles hold `EXECUTE` on write-capable `SECURITY DEFINER` functions.
18. Use catalogs and `has_*_privilege` functions to inspect effective privileges.
19. Author **positive tests** and **negative tests** for application and migration permissions.
20. Build workflows for credential rotation, revocations, environment separation, ownership transfers, and incident response.
21. Ensure role separation pairs with logging, auditing, resource limits, secret governance, and restore testing.

**Scope:** Modern PostgreSQL. Certain role-membership rules changed in PostgreSQL 16+, and logical replication, subscription worker checks, and cloud-managed PostgreSQL offerings differ by version and vendor. Always verify against your live cluster. Commands altering cluster-wide roles must run strictly in authorized environments.

---

## 2. Real-World Problem: One Account Does Everything

Suppose a system named `ShopCore` includes:

- A catalog read API.
- A cart/order update API.
- An inventory adjustment worker.
- A revenue reporting job.
- A Flyway/Liquibase schema migration pipeline.
- A physical standby for disaster recovery.
- A logical replica for analytics.
- Monitoring and backup tooling.

A flawed configuration:

```text
SHOP_DB_USER=postgres
SHOP_DB_PASSWORD=same-secret-everywhere
```

shared by every component.

### 2.1. Why Is This Dangerous?

If the catalog read API is compromised, its DB login gives attackers far more than read access:

- Modifying or deleting unrelated tables.
- Running `ALTER`/`DROP` on core tables.
- Reading payroll, customer PII, or internal secrets.
- Altering grants or creating admin roles.
- Bypassing RLS if superuser.
- Corrupting replication/backup config or disrupting availability.

### 2.2. Blast Radius

**Blast radius** is the maximum damage possible if one component is compromised.

Comparison:

| Compromised Credential | Under Least Privilege | Sharing Superuser |
| --- | --- | --- |
| Catalog API | Reads only exposed catalog views/columns | Accesses and alters virtually any object |
| Inventory worker | Updates only scoped stock columns | Drops/alters tables or reads unrelated tables |
| Migration pipeline | Modifies app schema per policy | Modifies cluster-wide configuration |
| Replication service | Streams replication data per protocol | Gains unneeded administrative SQL rights |
| BI dashboard | Reads reporting views only | Queries raw PII and internal tables directly |

### 2.3. One Credential Should Not Span Two Trust Boundaries

An internet-facing API and a CI/CD migration pipeline face totally different threat models. Even when developed in the same repository, they must never share DDL-capable login credentials.

### 2.4. Role Separation Alone Does Not Solve Everything

A read-only role with overly broad `SELECT` still leaks PII. A non-superuser replication login still handles sensitive cluster data. Design each role strictly around **permitted data and actions**.

---

## 3. PostgreSQL Roles: Three Distinct Dimensions

PostgreSQL uses a unified **role** abstraction, yet roles serve distinct functions.

### 3.1. Role Attributes

Example:

```sql
CREATE ROLE sample_login LOGIN;
CREATE ROLE sample_group NOLOGIN;
```

`LOGIN` allows direct session authentication under valid HBA/auth config. `NOLOGIN` forbids direct login while still allowing ownership and privilege grants.

Other critical attributes include `SUPERUSER`, `CREATEDB`, `CREATEROLE`, `REPLICATION`, and `BYPASSRLS`.

### 3.2. Object Privileges

Example:

```sql
GRANT SELECT ON TABLE app.orders TO app_reader;
GRANT UPDATE (stock) ON TABLE app.inventory TO inventory_writer;
```

These control access to specific database objects—completely distinct from cluster-level attributes like `REPLICATION` or `SUPERUSER`.

### 3.3. Role Membership

```sql
GRANT app_read TO catalog_api_login;
```

A login role acquires group permissions subject to inheritance and membership rules.

### 3.4. Ownership

Objects belong to an owner:

```sql
CREATE TABLE app.orders (...);
```

The creator role is normally the initial owner. Owners can alter definitions, drop objects, and manage grants per PostgreSQL rules—far more power than ordinary `SELECT`/`UPDATE` grants.

### 3.5. Administrative Attributes Do Not Inherit Like GRANT SELECT

Special role attributes such as `SUPERUSER`, `CREATEDB`, `CREATEROLE`, `LOGIN`, `REPLICATION`, and `BYPASSRLS` **are not inherited automatically like standard object privileges** merely through membership. `SET ROLE` and privilege escalation follow explicit rules—never assume group membership turns an app login into a valid replication account.

---

## 4. Duty-Based Privilege Matrix

This serves as a **starting blueprint**, not universal mandatory grants for every workload:

| Role | LOGIN | DDL / Owner | CRUD | Replication | Elevated Attributes |
| --- | --- | --- | --- | --- | --- |
| `cluster_admin` / break-glass | Yes, tightly governed | Very broad as needed | Very broad | Can administer | True superuser if self-managed |
| `migration_login` | Yes | Switches to `app_owner` when authorized | Strictly for migrate/backfill | No | No default superuser |
| `app_owner` | **No** | Owns app objects | Per owner semantics | No | No superuser |
| `catalog_api_login` | Yes | No | `SELECT` catalog views/columns | No | No |
| `order_api_login` | Yes | No | Scoped `INSERT`/`UPDATE`/`SELECT` | No | No |
| `inventory_worker_login` | Yes | No | Update `stock`, insert movements | No | No |
| `physical_repl_login` | Yes | No | Not used as SQL API | Yes | `REPLICATION`, non-superuser |
| `logical_repl_login` | Yes | No | `SELECT` published tables if needed | Yes | Logical replication needs only |
| `backup_login` | Tool-dependent | No | Read backup scope | If physical backup | Separate from runtime |
| `monitor_login` | Yes | No | Metrics / appropriate catalogs | Not by default | Predefined monitoring role as needed |

### 4.1. Administration and Migration Are Different Duties

A pipeline needing `ALTER TABLE app.orders` does not need `ALTER ROLE postgres SUPERUSER`.

### 4.2. Replication and API Traffic Are Different Duties

A physical standby needs WAL streaming, not `UPDATE app.orders` business logic. Conversely, a catalog API must never hold the `REPLICATION` attribute.

### 4.3. Separate Read and Write Roles

If a read-only service is breached, attackers should lack `INSERT`/`UPDATE`/`DELETE` on base tables. Write services can be constrained to specific columns or narrow functions.

### 4.4. Never Use the Object Owner as a Service Login

If runtime services connect as the object owner, they gain unnecessary DDL/GRANT powers and bypass RLS on owned tables by default.

### 4.5. Avoid Lumping Every Service Into One Broad Group

A single `all_shop_services` group holding `GRANT ALL ON ALL TABLES` defeats having separate login names.

---

## 5. Cluster Admin Roles: Intentional High Privilege

In self-managed PostgreSQL clusters, a true superuser holds sweeping capabilities, bypassing ordinary permission checks, RLS, and many administrative guardrails.

### 5.1. Appropriate Admin Tasks

- Initial cluster bootstrap.
- Managing sensitive cluster configuration.
- Cluster-wide incident intervention.
- Provisioning special role attributes or trusted extensions when required.
- Authorized disaster recovery tasks.

### 5.2. Tasks That Never Need Superuser

- Reading catalog items for APIs.
- Inserting customer orders.
- Updating stock counts.
- Running routine migrations inside app-owned schemas.
- Collecting routine metrics covered by predefined monitoring roles.

### 5.3. Keep Admin Accounts Out of Connection Pools

App connection pools hold many long-lived connections right next to untrusted user input—the worst place for top-tier credentials.

### 5.4. Break-Glass Accounts

Emergency administrative accounts require:

- Formal approval and audit trails.
- Credentials stored in a dedicated secret vault.
- Infrastructure access controls and administrative MFA where supported.
- Strict network restrictions.
- Post-use credential rotation per policy.
- Complete absence from `application.properties`, web app env vars, and CI logs.

### 5.5. Managed PostgreSQL Rarely Grants True Superuser

On cloud-managed PostgreSQL, accounts named `postgres` or `admin` often belong to provider-scoped admin roles rather than having `rolsuper = true`. Never infer privileges from account names.

---

## 6. Role Attributes Requiring Careful Evaluation

| Attribute | Purpose | Grant to Typical Runtime? |
| --- | --- | --- |
| `LOGIN` | Direct authentication | Yes, for runtime logins |
| `NOLOGIN` | Blocks direct login | Ideal for groups and object owners |
| `SUPERUSER` | Bypasses most permission checks | **No** |
| `CREATEROLE` | Administers roles per version rules | **No** |
| `CREATEDB` | Creates databases | **No** |
| `REPLICATION` | Replication connections/capabilities | **No** for APIs |
| `BYPASSRLS` | Bypasses row-level security | **No** for multi-tenant APIs |
| `INHERIT`/`NOINHERIT` | Governs automatic group inheritance | Depends on membership model |
| `CONNECTION LIMIT` | Caps concurrent role connections | Recommended operational limit |

### 6.1. CREATEROLE Expands Administrative Scope

Never grant `CREATEROLE` simply because migrations create tables. Role management and table management are distinct responsibilities.

### 6.2. BYPASSRLS Is Especially Dangerous in Multi-Tenant Apps

When tenant isolation relies on RLS, granting `BYPASSRLS` to a runtime login disables that boundary under PostgreSQL rules.

### 6.3. REPLICATION Carries Sensitive Scope

Physical replication is not "scoped column SELECT". WAL and base backups carry data across the whole cluster, creating both confidentiality and availability risks.

### 6.4. Role Names Create Zero Permissions

Naming a role `readonly` proves nothing. Inspect attributes, memberships, `GRANT`s, RLS, functions, and special privileges directly.

---

## 7. NOLOGIN Owners: Separating Ownership From Credentials

Standard design:

```sql
CREATE ROLE shop_owner NOLOGIN;
```

This role owns application schemas, tables, views, and functions—without holding a login password exposed to app containers.

### 7.1. Benefits

- Consistent DDL ownership across deployments.
- Runtime apps never hold owner rights merely to run CRUD.
- Default privileges bind cleanly to one consistent creator role.
- Migration pipelines can change without altering ownership of every table.
- Fewer credentials exist capable of mutating schema.

### 7.2. NOLOGIN Alone Does Not Prevent Abuse via SET ROLE

If a runtime login holds membership permitting `SET ROLE shop_owner`, it can still assume ownership privileges. **Never grant owner membership to runtime accounts.**

### 7.3. Schema Owners and Table Owners Can Differ

Owning a schema does not automatically let a role `ALTER`/`DROP` tables owned by another role in that schema. Enforce consistent creation ownership during migrations.

### 7.4. Owners Do Not Need Superuser

Most application objects can be created and maintained cleanly by a schema/object owner without superuser. Handle rare cluster-wide extensions or DDL separately via admin steps.

---

## 8. Migration Logins: DDL Capability Without Cluster Admin

A migration role typically needs:

- Login credentials stored strictly in CI/CD secret vaults.
- Membership permission to act as the `NOLOGIN` owner role.
- Authority to create/modify app tables, indexes, views, functions, and grants.
- Scoped backfill DML rights when scripts require data migrations.
- No `REPLICATION`, `BYPASSRLS`, or `SUPERUSER` unless explicitly justified.

### 8.1. Example Structure

```sql
CREATE ROLE shop_migration_login LOGIN NOINHERIT;
GRANT shop_owner TO shop_migration_login;
```

This is an illustrative layout; configure authentication credentials outside scripts and verify version-specific membership options.

### 8.2. Why NOINHERIT?

With appropriate membership settings, the migration login does not silently inherit owner powers unless it explicitly switches roles, enforcing clean DDL boundaries:

```sql
SET ROLE shop_owner;

CREATE TABLE shop_internal.example (
    id BIGINT PRIMARY KEY
);

RESET ROLE;
```

### 8.3. PostgreSQL 16+ Explicit Membership Options

PostgreSQL 16+ separates **`ADMIN`**, **`INHERIT`**, and **`SET`** options on role memberships, distinguishing passive privilege inheritance from `SET ROLE` switching.

For PostgreSQL 16+, configuration may look like:

```sql
GRANT shop_owner TO shop_migration_login
WITH INHERIT FALSE, SET TRUE;
```

Do not copy this syntax verbatim to older unsupported versions; verify version documentation and active grants.

### 8.4. Creator Role Governs Default Privileges

If a migration creates a table directly as `shop_migration_login` without running `SET ROLE shop_owner`, the new table becomes owned by the migration login and misses default ACLs attached to `shop_owner`—causing ownership drift and broken runtime grants.

### 8.5. Migrations Often Run DML Too

Backfills, index builds, constraint validation, and reference-data updates require DML privileges. Run them under the owner context during deployment rather than leaking DDL powers into app logins.

### 8.6. Keep Pipeline Secrets Out of App Secrets

Never inject `shop_migration_login` credentials into HTTP API containers or public app configs, and never run Flyway/Liquibase under runtime app logins out of convenience.

---

## 9. Running Migrations Under the Owner Identity

A clean migration flow:

```text
CI/CD:
  authenticate as shop_migration_login
  BEGIN
    SET ROLE shop_owner
    CREATE/ALTER objects
    GRANT runtime permissions
  COMMIT
  RESET ROLE / close connection
```

**Syntax note:** PostgreSQL supports `SET ROLE role_name` (and `SET LOCAL ROLE role_name` inside transactions in appropriate contexts). To minimize tool/driver surprises, examples here show explicit `SET ROLE` paired with clear transaction and connection cleanup.

### 9.1. Clean Example

```sql
BEGIN;

SET ROLE shop_owner;

-- CREATE/ALTER application objects.
-- ALTER TABLE shop_internal.orders ADD COLUMN ...;

COMMIT;

RESET ROLE;
```

Ensure the session holds permission to `SET ROLE shop_owner`. For non-transactional DDL such as `CREATE INDEX CONCURRENTLY`, migrations must split steps appropriately.

### 9.2. Never "Fix" Failed SET ROLE With SUPERUSER

If `SET ROLE` fails, fix role membership under least privilege—never add `SUPERUSER` as a shortcut.

### 9.3. Why RESET ROLE or Close the Connection?

A pooled connection still holding owner identity would execute subsequent statements with elevated rights. Run migrations on dedicated short-lived connections, reset roles cleanly, and close them afterward.

### 9.4. Who Controls Role Memberships?

Role-to-role `GRANT`s belong to provisioning/admin governance—never allow arbitrary migration scripts to grant themselves admin memberships.

---

## 10. Application Roles: Separating Read, Write, and Functional Scope

Avoid creating one monolithic `shop_app` role holding `GRANT ALL ON ALL TABLES`.

Prefer granular separation:

```text
shop_catalog_read (NOLOGIN)
         ^
         |
catalog_api_login (LOGIN)

shop_order_write (NOLOGIN)
         ^
         |
order_api_login (LOGIN)

shop_inventory_write (NOLOGIN)
         ^
         |
inventory_worker_login (LOGIN)
```

### 10.1. Read Services Need Zero DDL

A catalog API typically needs strictly:

- `CONNECT` on the database.
- `USAGE` on exposed schemas.
- `SELECT` on public views or specific columns.

Never grant `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE`, or `GRANT` options.

### 10.2. Order Writing Does Not Require All Tables

The order API may insert into `orders`/`order_items`, read reference records, and update bounded status columns—without needing `DELETE` on `customers` or `UPDATE` on `unit_cost`.

### 10.3. Inventory Workers Do Not Need Customer PII

A stock worker needs SKUs, stock counts, transaction IDs, and movement tables—never grant `SELECT` on `customer_email` merely because tables share a schema.

### 10.4. Never Grant Write Groups to Readers

Making a read-only catalog login a member of `shop_order_write` undermines narrow view ACLs immediately.

### 10.5. Pair Application Roles With Resource Controls

Even a strictly read-only role can run heavy queries exhausting CPU, I/O, or locks. Enforce `statement_timeout`, connection limits, quotas, and monitoring to protect availability.

---

## 11. Physical Replication: A Distinct Trust Boundary

PostgreSQL **physical streaming replication** ships WAL records so a standby replays storage-level cluster changes, closely mirroring primary state.

```text
Primary (WAL producer)
      |
      | WAL sender + replication protocol
      v
Network channel (TLS / allowlist)
      |
      v
Physical standby (WAL receiver/replay)
```

### 11.1. What Does a Physical Replication Role Need?

On the primary, a login holding the `REPLICATION` attribute (or superuser) connects via the replication protocol subject to `pg_hba.conf` authentication and system limits.

Privileged provisioning example (never run in active clusters without approval):

```sql
-- Illustrative; create strictly via approved DBA workflow:
-- CREATE ROLE physical_repl_login LOGIN REPLICATION;
```

Manage credentials, network rules, and client certificates outside source code.

### 11.2. REPLICATION Is a Role Attribute, Not GRANT SELECT

Running:

```sql
GRANT SELECT ON some_table TO physical_repl_login;
```

does not enable streaming WAL. Conversely, holding `REPLICATION` must never turn that role into a routine application SQL account.

### 11.3. Why Is Physical Replication So Sensitive?

Physical WAL streams contain changes across every database in the cluster, including sensitive PII and secrets—completely bypassing API views and column-level `SELECT` rules.

### 11.4. Never Share Credentials With Applications

Treat compromise of `physical_repl_login` as a replication/data-exfiltration incident, not merely a leaked API key.

### 11.5.Dedicated REPLICATION Logins Avoid True Superuser

Using a dedicated `LOGIN REPLICATION` role avoids giving standby hosts full cluster superuser powers—while still treating `REPLICATION` as a **high-sensitivity privilege**.

---

## 12. Securing Replication Connections: pg_hba.conf, TLS, and Networks

PostgreSQL enforces layered connection security:

- Firewalls, VPCs, and security groups.
- `pg_hba.conf` authentication rules.
- TLS encryption and endpoint verification.
- Role attributes and strong credentials.
- WAL sender and replication parameters.
- Replication slot management permissions.

### 12.1. Example pg_hba Entry for Physical Replication

Illustrative line in primary `pg_hba.conf`:

```conf
# TYPE     DATABASE       USER                 ADDRESS          METHOD
hostssl    replication    physical_repl_login  10.20.30.40/32   scram-sha-256
```

Physical replication uses the special `replication` keyword in the DATABASE field.

### 12.2. Never Allow Wide Subnets

Permitting `0.0.0.0/0` for replication logins exposes critical attack surface. Restrict rules to specific standby IPs and verify endpoints properly.

### 12.3. Enforce Endpoint Verification Alongside TLS

`hostssl` mandates SSL/TLS on the server side, yet clients must also enable strict certificate/hostname validation (`verify-full`) to defeat server spoofing.

### 12.4. Related Server Settings

Physical replication relies on parameters such as:

```sql
SHOW wal_level;
SHOW max_wal_senders;
SHOW max_replication_slots;
```

Size settings cleanly for your topology; blindly inflating limits does not improve availability.

### 12.5. pg_hba Does Not Replace Credential Security

IP restrictions help, yet credentials still need rotation and vault storage—compromise of a standby host places the attacker right inside the IP allowlist.

---

## 13. Physical Standbys, Base Backups, and Privileges

Standbys initialize via tools like `pg_basebackup`, followed by streaming WAL.

### 13.1. Physical Backups Differ From Logical Dumps

Physical base backups capture cluster-wide storage files per tool mechanics, not scoped `SELECT` exports.

### 13.2. Backup Roles Using the Replication Protocol

Depending on your backup tool, the backup login may require `REPLICATION` and specific functions without requiring `SUPERUSER`. Align exact rights with tool and version docs.

### 13.3. Never Use Standby Credentials for App DDL

Never grant app DDL/CRUD simply because a standby agent connects. Keep admin/DDL channels separate from replication.

### 13.4. Secure Backup Artifacts and WAL Archives

Backups and archived WAL hold full cluster data outside PostgreSQL's SQL ACLs. Enforce encryption, tight storage ACLs, retention rules, and download audits on backup buckets.

### 13.5. Only Restore Drills Prove Recoverability

A clean backup job does not guarantee restores preserve target timing, roles, owners, grants, or RLS state. Test restores routinely including verification of target privileges and credentials.

---

## 14. Physical Replication Does Not Replace Primary Access Control

A standby mirrors physical data; it does not hide sensitive tables from standby admins.

### 14.1. RLS Does Not Filter Physical WAL Streams

RLS filters SQL queries over tables; physical replication runs below SQL at the WAL layer. Never rely on RLS to stop a physical standby from replicating other tenants.

### 14.2. Replication Lag Affects Application Reads

Standbys can lag behind the primary. Applications reading from replicas must account for consistency expectations (such as read-your-writes after order placement).

### 14.3. Synchronous Replication Affects Availability

Under synchronous replication, primary commits block awaiting standby acknowledgment per configuration, coupling HA and network availability directly to writes.

### 14.4. Replication Logins Are Not User Audit Identities

Standby agents mirror writes originated on the primary without representing business users. Perform user/action auditing on the primary and application gateway.

---

## 15. Logical Replication: Different Scope and Privileges From Physical

**Logical replication** streams relation/row changes via publications and subscriptions, typically syncing selected tables from publisher to subscriber.

```text
Publisher database
   |
   +-- publication: published tables and config
   |
   +-- logical decoding / replication protocol
   |
   v
Subscriber database
   |
   +-- subscription
   +-- apply worker
   +-- prepared target tables
```

### 15.1. Logical Replication Is Not Inherently "Minimal Safe Columns"

Publications can replicate wide tables containing PII. An overly broad publication pushes sensitive records into downstream destinations lacking equivalent controls.

### 15.2. Publication and Subscription Ownership Are Managed Separately

Creating/modifying publications and subscriptions, table ownership, replication login rights, and target table permissions all follow PostgreSQL version-specific rules.

Never assume "holding `REPLICATION` lets a role run `CREATE PUBLICATION` on any table" or "holding `SELECT` allows running `CREATE SUBSCRIPTION` arbitrarily".

### 15.3. Appropriate Use Cases for Logical Replication

- Streaming selected tables for analytics.
- Syncing tables across PostgreSQL databases as required.
- Zero/low-downtime major upgrades or migrations.
- Offloading analytical queries from OLTP primaries.

### 15.4. When Logical Replication Is Not Suitable

For cluster-wide physical HA standbys and PITR, logical replication does not directly replace physical replication.

### 15.5. Secure Both Publisher and Subscriber

Lock down publication rights on the publisher alongside received tables, stored connection strings, schemas, and apply workers on the subscriber.

---

## 16. Logical Replication Roles on the Publisher

Logical subscribers typically connect via a dedicated replication login.

**Non-runnable administrative example:**

```sql
-- DBA provisioning:
-- CREATE ROLE logical_repl_login LOGIN REPLICATION;
--
-- Grant table SELECT needed for initial table sync
-- per exact PostgreSQL version and tooling docs:
-- GRANT USAGE ON SCHEMA source_schema TO logical_repl_login;
-- GRANT SELECT ON TABLE source_schema.orders TO logical_repl_login;
```

### 16.1. Initial Table Synchronization

When subscriptions copy baseline table data, initial sync workers require read rights on published tables alongside replication protocol rights. Granting `REPLICATION` alone without `SELECT` causes initial sync to fail.

### 16.2. Scope SELECT Strictly to Published Tables

Never grant `SELECT ON ALL TABLES IN SCHEMA internal` when a publication only covers two tables—otherwise PII or secret tables inside that schema become exposed.

### 16.3. RLS and Logical Replication

Logical replication enforces specific checks around RLS, execution roles, and publisher evaluation. Some setups reject replication by default when the role is subject to RLS to prevent silent filtering bugs; test carefully under exact roles and versions.

**Never** blindly grant `BYPASSRLS` just to silence a subscription error—that removes tenant isolation boundaries elsewhere.

### 16.4. Never Reuse logical_repl_login for Apps

It represents a replication transport identity, never an end-user service role.

---

## 17. Publications: Controlling Exactly Which Tables Leave Primary

Conceptual example on publisher:

```sql
CREATE PUBLICATION shop_analytics_pub
FOR TABLE
    analytics_source.orders,
    analytics_source.order_items;
```

Assumes the schema and tables exist and the executing role holds publication creation rights over them.

### 17.1. Distinction Between Publications and GRANT SELECT

Publications define which logical changes enter the WAL decoding stream; `SELECT` governs SQL reads and initial snapshot sync. They operate independently.

### 17.2. Specify Explicit Tables Over "All Tables" When Scope Is Narrow

`FOR ALL TABLES` automatically includes future tables added to the database, risking silent exposure of new sensitive tables. List explicit tables and review schema migrations.

### 17.3. Column Lists and Row Filters

Modern PostgreSQL versions add column lists and row filters on publications. Still, these carry constraints around replica identity, `UPDATE`/`DELETE` semantics, and versions—never treat publication filters as an SQL authorization equivalent to RLS.

### 17.4. DDL Does Not Automatically Replicate Like Row Data

Standard logical replication does not automatically propagate schema changes to subscribers. Coordinate subscriber migrations whenever the publisher alters tables or columns.

### 17.5. Replica Identity

`UPDATE`/`DELETE` replication often relies on appropriate `REPLICA IDENTITY` settings, impacting WAL volume, performance, and transmitted column values.

---

## 18. Subscriptions: Subscriber-Side Privileges

On the subscriber, a subscription connects to the publisher:

```sql
CREATE SUBSCRIPTION shop_analytics_sub
CONNECTION 'host=publisher.internal port=5432 dbname=shop user=logical_repl_login ...'
PUBLICATION shop_analytics_pub;
```

This is a **syntax illustration**, not copy-paste DDL: load credentials safely outside scripts, verify TLS/privileges, and ensure target tables exist. Never commit real passwords into migrations, shell history, or repos.

### 18.1. Creating Subscriptions Requires Specific Privileges Distinct From CREATE TABLE

Depending on PostgreSQL version, creating/owning subscriptions and running apply workers relies on specialized privileges or predefined roles introduced in newer versions. Verify exact docs rather than assuming legacy behavior.

### 18.2. Apply Workers and Target Table Write Rights

Subscriptions apply changes into subscriber tables. Interaction among the subscription owner, table owners, and apply worker security rules varies across versions (`run_as_owner`, etc.).

### 18.3. Subscription Owners Should Never Be Web API Logins

Web APIs must never hold permissions to edit publisher connection strings, drop subscriptions, or tamper with sync pipelines.

### 18.4. Protect Stored Connection Strings

Subscription connection strings often contain credentials stored in catalog metadata. Restrict who can read or alter subscription definitions per version docs.

### 18.5. Check Subscriber-Side Triggers and RLS

Logical apply workers follow distinct behaviors around replication origins, `ENABLE REPLICA` triggers, and table security. Never assume subscriber inserts traverse identical paths to direct client SQL.

---

## 19. Logical Replication Is Not Complete Tenant Authorization

Suppose analytics may access strictly tenant 10 data.

### 19.1. Risk of Overly Broad Publications

If the publisher streams every tenant's `orders` rows to the analytics subscriber, giving BI users `SELECT` only for tenant 10 **does not stop all tenants' data from already sitting on the subscriber**.

### 19.2. Protect Replicated Data According to Classification

Harden subscribers matching the highest classification of replicated data: disk encryption, backups, monitoring ACLs, BI grants, network segmentation, and RLS.

### 19.3. Limits of Publication Row Filters

Even with publication row filters, inspect initial sync, `UPDATE`/`DELETE` edge cases, schema changes, and grants rather than trusting row filters as a sole boundary.

### 19.4. Separate Transport Accounts From Consumer Accounts

Replication moves data operationally; grant analyst read permissions separately on subscriber databases rather than reusing replication accounts.

---

## 20. Replication Slots: Availability Risks From Misused Credentials

**Replication slots** tell PostgreSQL how far back WAL segments must be retained for consumers.

### 20.1. Physical Slots

Prevent primary WAL recycling needed by lagging or disconnected physical standbys.

### 20.2. Logical Slots

Preserve WAL required by logical decoding consumers/subscribers.

### 20.3. Stalled Consumers Hold WAL Indefinitely

If a consumer stops advancing its slot, WAL accumulates on primary until disk fills. `max_wal_size` does not override active slot retention requirements.

### 20.4. Why Is This a Security Concern?

Compromising or misusing a `REPLICATION` login lets an adversary create or stall slots to exhaust primary disk space (denial of service) or tap data streams. Pair least privilege with slot monitoring, `max_slot_wal_keep_size`, and lifecycle alerts.

### 20.5. Inspecting Slots

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_catalog.pg_replication_slots
ORDER BY slot_name;
```

Columns may be `NULL` depending on slot type or state; visibility depends on privileges and version.

### 20.6. Never Drop Slots Blindly During an Incident

Dropping a slot strands consumers past retained WAL, forcing full re-synchronization or breaking failover readiness. Identify consumer owners, lag, retention, and recovery plans first.

---

## 21. Physical vs. Logical Replication: Privilege Comparison

| Aspect | Physical Replication | Logical Replication |
| --- | --- | --- |
| Data unit | Cluster WAL / storage blocks | Table/row logical changes |
| Typical scope | Whole cluster / physical instance | Selected tables per publication |
| Publisher login | `LOGIN REPLICATION` or suitable role | `LOGIN REPLICATION` plus table reads as needed |
| Sensitive exposure | Cluster-wide | Scoped by publication, still sensitive |
| Initial table `SELECT` needed? | Not SQL table copy | Initial sync typically requires `SELECT` |
| Schema changes | Replicated physically with cluster | DDL coordinated separately |
| RLS filters stream per user? | No | Subject to specific rules; not tenant auth |
| Replication slots | Optional / recommended | Normally required |
| Subscriber app grants | Managed per subscriber needs | Managed separately |
| Primary purpose | HA, DR, physical backups | Analytics, CDC, selective sync/upgrades |

**Neither account should ever be used by HTTP application logins.**

---

## 22. Keep Backup and Monitoring Roles Separate Too

Two commonly overlooked roles:

### 22.1. Backup

Logical dumps (`pg_dump`) need `SELECT` on data, sequences, and metadata, whereas physical backups (`pg_basebackup`) stream raw files via replication protocol. Design **backup roles per backup method**.

### 22.2. Monitoring

Monitoring systems typically collect:

- Connection counts and backend states.
- Replication lag.
- WAL generation and retention.
- Lock contention and table bloat stats.
- Disk space and autovacuum progress.

Monitoring never needs `SELECT` on customer PII tables or `UPDATE` on orders.

### 22.3. Predefined Roles

Consider PostgreSQL predefined monitoring roles:

- `pg_monitor`.
- `pg_read_all_stats`.
- `pg_read_all_settings`.

Each grants notable visibility; pick the narrowest role required by your dashboards. Never grant `pg_read_all_data` just to measure replication lag.

### 22.4. Protect Telemetry Data

Statistics views and query text can reveal table layouts or sensitive literals. Review monitoring grants alongside logging/redaction policies.

---

## 23. Safe Lab: Separating Owner, Migration, and Runtime Roles

This lab uses `NOLOGIN` roles to simulate boundaries **without creating superusers or replication logins**. `CREATE ROLE` still requires administrative privileges, so run strictly inside an authorized lab database.

Assume a fresh lab database without existing objects below.

**Lab goals:**

- Owner does not log in directly.
- Migrator can switch to owner via membership to run DDL.
- Reader reads strictly the catalog view.
- Writer reads `sku`/`stock` and updates `stock` only.
- Reader cannot read `unit_cost`/`internal_note` or mutate rows.
- Verify effective privileges.
- Observe ownership and default privilege mechanics.

### 23.1. Create Roles

```sql
-- Lab environment only, with role-management privileges:
CREATE ROLE sec392_owner NOLOGIN;

CREATE ROLE sec392_migrator NOLOGIN NOINHERIT;

CREATE ROLE sec392_read_group NOLOGIN;
CREATE ROLE sec392_write_group NOLOGIN;

CREATE ROLE sec392_reader NOLOGIN INHERIT;
CREATE ROLE sec392_writer NOLOGIN INHERIT;

-- Migrator may assume owner identity via membership.
GRANT sec392_owner TO sec392_migrator;

-- App roles inherit strictly their assigned functional groups.
GRANT sec392_read_group TO sec392_reader;
GRANT sec392_write_group TO sec392_writer;
```

**Why make lab actor roles NOLOGIN?** We avoid storing passwords in scripts; an authorized admin simulates actors using `SET ROLE`. Production uses real `LOGIN` roles with managed vault credentials.

### 23.2. Membership Evaluation Note

On PostgreSQL 16+, verify `INHERIT`/`SET` options if cluster policies override defaults. This lab expects `reader` and `writer` to inherit their respective groups.

### 23.3. Create Schema Owned by the Owner Role

```sql
CREATE SCHEMA sec392_lab
AUTHORIZATION sec392_owner;
```

Uses a dedicated lab schema rather than `public`.

### 23.4. Create Table While Acting as Owner

In a permitted admin session:

```sql
SET ROLE sec392_owner;

CREATE TABLE sec392_lab.products (
    sku TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    stock INTEGER NOT NULL
        CONSTRAINT sec392_products_stock_nonnegative
        CHECK (stock >= 0),
    unit_cost NUMERIC(12,2) NOT NULL
        CONSTRAINT sec392_products_cost_nonnegative
        CHECK (unit_cost >= 0),
    internal_note TEXT
);

INSERT INTO sec392_lab.products (
    sku,
    display_name,
    stock,
    unit_cost,
    internal_note
)
VALUES
    ('SKU-A', 'Keyboard', 12, 300000.00, 'Supplier Alpha'),
    ('SKU-B', 'Mouse',    40,  95000.00, 'Supplier Beta'),
    ('SKU-C', 'Monitor',   5, 1900000.00, NULL);

RESET ROLE;
```

### 23.5. Resulting State

`sec392_lab.products` is owned by `sec392_owner`. Neither `reader` nor `writer` can read it yet simply because it exists.

---

## 24. Lab: Catalog View as a Scoped Read Interface

The catalog API needs only `sku`, `display_name`, and `stock`, omitting `unit_cost` and `internal_note`.

```sql
SET ROLE sec392_owner;

CREATE VIEW sec392_lab.v_catalog AS
SELECT
    sku,
    display_name,
    stock
FROM sec392_lab.products;

COMMENT ON VIEW sec392_lab.v_catalog
IS 'Catalog read model: public product identifiers, display names and stock; excludes unit cost and internal notes.';

RESET ROLE;
```

### 24.1. Why Use a View?

- Stable `SELECT` interface.
- Restricts exposed columns.
- Decouples clients from internal base table structures.
- Grants view `SELECT` without exposing direct base-table `SELECT` under default owner-based view semantics.

### 24.2. A View Alone Does Not Guarantee Authorization

If the role retains base-table `SELECT` via another path, it can still query `unit_cost`. Always check direct grants, group memberships, and `PUBLIC`.

### 24.3. View Ownership and RLS

Default views check underlying access as the view owner, affecting RLS. In multi-tenant databases, evaluate `security_invoker` deliberately rather than assuming views isolate tenants automatically.

---

## 25. Lab: Grant Separate Read and Write Privileges

### 25.1. Schema USAGE

```sql
SET ROLE sec392_owner;

GRANT USAGE ON SCHEMA sec392_lab
TO sec392_read_group, sec392_write_group;
```

### 25.2. Reader Gets View SELECT Only

```sql
GRANT SELECT ON sec392_lab.v_catalog
TO sec392_read_group;
```

### 25.3. Writer Gets Column-Scoped SELECT and UPDATE

```sql
GRANT SELECT (sku, stock),
      UPDATE (stock)
ON TABLE sec392_lab.products
TO sec392_write_group;

RESET ROLE;
```

### 25.4. Never Grant Owner Membership to Runtime Roles

Notice we **do not** run:

```sql
-- Never do this:
-- GRANT sec392_owner TO sec392_reader;
-- GRANT sec392_owner TO sec392_writer;
```

Giving runtime roles `SET ROLE` into the owner defeats ownership separation completely.

### 25.5. Never Grant ALL TABLES Out of Habit

```sql
-- Avoid as a default pattern:
-- GRANT ALL ON ALL TABLES IN SCHEMA sec392_lab
-- TO sec392_read_group, sec392_write_group;
```

Blanket grants needlessly widen each role's scope.

---

## 26. Lab: Testing Reader Privileges

**Positive test:**

```sql
SET ROLE sec392_reader;

SELECT sku, display_name, stock
FROM sec392_lab.v_catalog
ORDER BY sku;

RESET ROLE;
```

`sec392_reader` reads `v_catalog` cleanly via `sec392_read_group`.

### 26.1. Negative Test: Reading unit_cost Fails

Run in an isolated authorized test session:

```sql
SET ROLE sec392_reader;

-- Expected permission denied:
SELECT sku, unit_cost
FROM sec392_lab.products;

RESET ROLE;
```

Remember that inside a transaction, any error puts the transaction into an aborted state needing `ROLLBACK` before issuing further statements. In automated test suites, run negative tests in separate transactions or sessions.

### 26.2. Negative Test: UPDATE Fails

```sql
SET ROLE sec392_reader;

-- Expected permission denied:
UPDATE sec392_lab.products
SET stock = stock + 1
WHERE sku = 'SKU-A';

RESET ROLE;
```

### 26.3. Negative Test: CREATE TABLE Fails

```sql
SET ROLE sec392_reader;

-- Expected permission denied:
CREATE TABLE sec392_lab.unexpected_table (id INTEGER);

RESET ROLE;
```

The reader holds `USAGE`, not `CREATE`.

### 26.4. Selecting a View Does Not Imply Base-Table SELECT

With owner-based views and proper grants, callers can read view columns without holding base-table `SELECT`—providing a read-only facade while still requiring ownership and RLS review.

### 26.5. Verify Under the Real Role

Run every positive and negative test under the application's actual effective role. Superusers bypass restrictions and prove nothing about runtime boundaries.

---

## 27. Lab: Testing Writer Privileges

### 27.1. Reading Stock

```sql
SET ROLE sec392_writer;

SELECT sku, stock
FROM sec392_lab.products
ORDER BY sku;

RESET ROLE;
```

### 27.2. Conditional UPDATE Inside a Rolled-Back Transaction

```sql
BEGIN;

SET ROLE sec392_writer;

UPDATE sec392_lab.products
SET stock = stock - 2
WHERE sku = 'SKU-A'
  AND stock >= 2
RETURNING sku, stock;

ROLLBACK;
```

Updates stock cleanly within the test transaction; `ROLLBACK` restores the original stock count.

### 27.3. Why Grant Both SELECT and UPDATE?

The query reads `stock` in the arithmetic expression and `WHERE`, and references `sku` in `WHERE` and `RETURNING`, requiring column `SELECT` alongside `UPDATE (stock)`.

### 27.4. Negative Test: Modifying unit_cost Fails

```sql
SET ROLE sec392_writer;

-- Expected permission denied:
UPDATE sec392_lab.products
SET unit_cost = 1
WHERE sku = 'SKU-A';

RESET ROLE;
```

### 27.5. Negative Test: DROP TABLE Fails

```sql
SET ROLE sec392_writer;

-- Expected permission denied:
DROP TABLE sec392_lab.products;

RESET ROLE;
```

Because `writer` neither owns the table nor holds DDL privileges.

### 27.6. Constraints Remain Essential

`CHECK (stock >= 0)` protects invariants across all write paths. Least privilege never replaces integrity constraints, nor should writes skip atomic conditional guards under concurrent updates.

---

## 28. Lab: Inspecting Catalog Metadata and Effective Privileges

### 28.1. Inspect Role Attributes

```sql
SELECT
    rolname,
    rolcanlogin,
    rolsuper,
    rolcreatedb,
    rolcreaterole,
    rolreplication,
    rolbypassrls,
    rolinherit
FROM pg_catalog.pg_roles
WHERE rolname LIKE 'sec392_%'
ORDER BY rolname;
```

Expect all lab roles to show `NOLOGIN`, non-`SUPERUSER`, non-`REPLICATION`, and non-`BYPASSRLS`.

### 28.2. Inspect Schema Owner

```sql
SELECT
    nspname,
    pg_catalog.pg_get_userbyid(nspowner) AS owner
FROM pg_catalog.pg_namespace
WHERE nspname = 'sec392_lab';
```

### 28.3. Inspect Table / View Owners

```sql
SELECT
    c.relname,
    c.relkind,
    pg_catalog.pg_get_userbyid(c.relowner) AS owner
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname = 'sec392_lab'
  AND c.relkind IN ('r','p','v','m','S')
ORDER BY c.relname;
```

### 28.4. Schema Privileges

```sql
SELECT
    pg_catalog.has_schema_privilege(
        'sec392_reader', 'sec392_lab', 'USAGE'
    ) AS reader_has_schema_usage,
    pg_catalog.has_schema_privilege(
        'sec392_writer', 'sec392_lab', 'USAGE'
    ) AS writer_has_schema_usage;
```

### 28.5. Table and Column Privileges

```sql
SELECT
    pg_catalog.has_table_privilege(
        'sec392_reader', 'sec392_lab.v_catalog', 'SELECT'
    ) AS reader_can_select_view,
    pg_catalog.has_column_privilege(
        'sec392_writer', 'sec392_lab.products',
        'stock', 'UPDATE'
    ) AS writer_can_update_stock,
    pg_catalog.has_column_privilege(
        'sec392_writer', 'sec392_lab.products',
        'unit_cost', 'UPDATE'
    ) AS writer_can_update_cost;
```

Expect `TRUE`, `TRUE`, and `FALSE` assuming no unexpected extra grants exist.

### 28.6. Metadata Checks Do Not Replace Negative Execution Tests

Hidden group memberships, `PUBLIC` grants, views, or functions can expose indirect paths. Pair `has_*` metadata audits with live negative tests under real roles.

---

## 29. Role Memberships: Never Audit Only Direct GRANTs

Suppose `catalog_api_login` holds `shop_catalog_read`, yet is also a member of `shop_all_write`—granting unintended write access indirectly.

### 29.1. Inspecting Role Memberships

```sql
SELECT
    member.rolname AS member_role,
    parent.rolname AS granted_role,
    grantor.rolname AS grantor_role,
    m.admin_option
FROM pg_catalog.pg_auth_members AS m
JOIN pg_catalog.pg_roles AS member
  ON member.oid = m.member
JOIN pg_catalog.pg_roles AS parent
  ON parent.oid = m.roleid
JOIN pg_catalog.pg_roles AS grantor
  ON grantor.oid = m.grantor
WHERE member.rolname LIKE 'sec392_%'
ORDER BY member_role, granted_role;
```

From PostgreSQL 16 onward, `pg_auth_members` also tracks `inherit_option` and `set_option`. Check version columns when authoring audit queries.

### 29.2. Never Grant Owner Membership to Runtime Accounts

Allowing runtime roles to `SET ROLE` into an owner turns passive runtime credentials into full DDL/owner credentials.

### 29.3. Watch Multi-Hop Membership Chains

`role A → role B → role C` can pass permissions indirectly depending on inheritance options. Audit the full membership graph, not just one hop.

### 29.4. ADMIN OPTION vs INHERIT / SET

- `ADMIN`: allows managing grants of that membership.
- `INHERIT`: automatically applies privileges without needing `SET ROLE`.
- `SET`: allows switching via `SET ROLE` when permitted.

These options are distinct and non-interchangeable.

---

## 30. Default Privileges: Prevent Permission Denied on New Migrations

Tables created by new migrations do not automatically copy grants from older tables.

### 30.1. GRANT on Existing Objects

```sql
GRANT SELECT ON ALL TABLES IN SCHEMA shop_reports
TO shop_report_reader;
```

Affects objects already existing at execution time.

### 30.2. ALTER DEFAULT PRIVILEGES for Future Objects

```sql
ALTER DEFAULT PRIVILEGES
FOR ROLE shop_owner
IN SCHEMA shop_reports
GRANT SELECT ON TABLES TO shop_report_reader;
```

Applies to tables/views created **in the future** by `shop_owner` inside `shop_reports`.

### 30.3. Creator Role Must Match Exactly

If the CI pipeline skips `SET ROLE shop_owner` and creates tables as `migration_login`, default privileges registered `FOR ROLE shop_owner` **will not apply**.

### 30.4. Avoid Blanket Default SELECT on Sensitive Schemas

If a schema contains PII or secret tables, default `GRANT SELECT ON TABLES` may accidentally open future internal tables. Isolate public views into dedicated schemas or assign object grants explicitly.

### 30.5. Default Privileges for Functions and Sequences

Default grants also cover functions and sequences—remember functions default to `PUBLIC EXECUTE` unless revoked, and sequences follow separate rules.

### 30.6. Default Privileges Are Not Retroactive

Updating policy requires auditing both existing objects and future defaults; `ALTER DEFAULT PRIVILEGES` alone never alters grants on older objects.

---

## 31. Migration Role in Live Practice

To observe creator/owner linkage:

```sql
-- Assuming session is authorized to SET ROLE sec392_owner:
SET ROLE sec392_owner;

CREATE TABLE sec392_lab.migration_marker (
    marker_id INTEGER PRIMARY KEY,
    description TEXT NOT NULL
);

RESET ROLE;
```

`migration_marker` becomes owned by `sec392_owner`.

### 31.1. What Happens When Created Under Another Role?

If a deployment login stays as `current_user` during `CREATE TABLE`, new tables become owned by the deployment login rather than the `NOLOGIN` owner—causing:

- Future migrations under the standard owner failing with `permission denied`.
- Owner-scoped default ACLs failing to fire.
- Views/functions owned by the owner unexpectedly lacking underlying rights.
- Inconsistent RLS/ownership bypass behavior.

### 31.2. Why Apps Should Not Run Migrations on Startup

App startups happen across scaled containers using runtime pools. Giving every web pod DDL permissions widens blast radius and invites concurrent DDL races.

### 31.3. Run Deployments via Isolated Short-Lived Connections

Never leave owner-switched sessions sitting inside runtime pools; close migration connections once deployment finishes.

---

## 32. PUBLIC and Default Permissions on Functions and Schemas

In PostgreSQL, `PUBLIC` represents every existing and future role.

### 32.1. Never Confuse PUBLIC With the public Schema

- `PUBLIC` in `GRANT`/`REVOKE`: pseudo-role meaning all roles.
- `public`: a concrete schema name.

### 32.2. Default Function EXECUTE

PostgreSQL grants `EXECUTE` on newly created functions to `PUBLIC` by default unless altered via default privileges.

A `SECURITY DEFINER` function with side effects left open to `PUBLIC EXECUTE` creates a serious privilege-escalation bug.

### 32.3. Create and Lock Down Grants Atomically

Conceptual pattern:

```sql
BEGIN;

CREATE FUNCTION shop_internal.do_sensitive_work(...)
RETURNS ...
LANGUAGE plpgsql
SECURITY DEFINER
AS $fn$
BEGIN
    -- ...
END;
$fn$;

REVOKE ALL ON FUNCTION shop_internal.do_sensitive_work(...)
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION shop_internal.do_sensitive_work(...)
TO shop_authorized_worker;

COMMIT;
```

This is a **structural skeleton**; replace `...` placeholders with valid definitions. Keeping CREATE, REVOKE, and GRANT in one transaction avoids leaving an open `PUBLIC` window. Do not run placeholders verbatim.

### 32.4. The public Schema in PostgreSQL 15+

Newly initialized PostgreSQL 15+ databases lock down default `CREATE` on `public` for `PUBLIC`. Upgraded or restored legacy databases often keep old ACLs—always check live ACLs, especially regarding `search_path`.

### 32.5. Revoking From PUBLIC Does Not Undo Other Paths

If a role receives `SELECT` via group membership or direct grants, `REVOKE SELECT ... FROM PUBLIC` does not remove that access. Privileges union across all active paths.

---

## 33. Sequences, Identity Columns, and DEFAULT nextval

Application `INSERT` operations frequently require sequence grants alongside table grants.

### 33.1. SERIAL / DEFAULT nextval

Example:

```sql
CREATE SEQUENCE shop_internal.order_id_seq;

CREATE TABLE shop_internal.orders (
    id BIGINT PRIMARY KEY
        DEFAULT nextval('shop_internal.order_id_seq'::REGCLASS)
);
```

Insert roles typically need `USAGE` on the sequence to evaluate `nextval`.

### 33.2. Sequence-Specific GRANT

```sql
GRANT USAGE ON SEQUENCE shop_internal.order_id_seq
TO shop_order_writer;
```

### 33.3. IDENTITY Columns Have Different Semantics

`GENERATED ... AS IDENTITY` columns obey internal ownership semantics distinct from explicit `DEFAULT nextval(...)`. Never assume identical sequence grant behavior across both; test directly on your PostgreSQL version.

### 33.4. Avoid Blanket USAGE ON ALL SEQUENCES

An order writer does not need access to billing or internal customer sequences.

### 33.5. Sequences Do Not Roll Back With Transactions

Rolled-back inserts still consume sequence numbers, producing gaps—do not misread normal sequence gaps as missing records or tampering.

---

## 34. SECURITY DEFINER Functions: Indirect Permission Paths

A role lacking direct `UPDATE` on a table can still mutate data if granted `EXECUTE` on an owner-privileged function.

### 34.1. Pattern

```text
inventory_worker_login
         |
         | EXECUTE reserve_stock(sku, qty)
         v
SECURITY DEFINER function (owner)
         |
         +--> UPDATE inventory.stock
         +--> INSERT stock_movements
```

This works cleanly when the function encapsulates **one tightly scoped business capability**.

### 34.2. Risks

Allowing arbitrary table names via dynamic SQL or trusting caller-supplied tenant IDs lets callers abuse owner privileges well outside contract.

### 34.3. Safe search_path and Hardening

For `SECURITY DEFINER`:

- Schema-qualify critical tables and functions.
- Pin `SET search_path` strictly to trusted schemas.
- Put `pg_temp` last to block temp-table shadowing.
- Exclude schemas where untrusted users hold `CREATE` ahead of trusted schemas.
- Scope `EXECUTE` strictly to authorized roles.
- Audit inputs, error messages, side effects, and RLS interactions.

### 34.4. Audit EXECUTE When Assessing "Read-Only" Roles

A "read-only" role allowed to `EXECUTE` a `SECURITY DEFINER` routine performing `INSERT`/`UPDATE` **is not truly read-only overall**.

### 34.5. Never Strip SECURITY DEFINER Just for Inlining

`SECURITY DEFINER` inhibits SQL function inlining because it enforces a security boundary—never remove it solely to chase a planner optimization without redesigning permissions.

---

## 35. RLS Across Owners, Runtime Roles, and Replication

RLS restricts rows cleanly, subject to major exceptions.

### 35.1. Table Owners Bypass RLS by Default

Owners skip RLS enforcement on their own tables unless forced. Separating `NOLOGIN` owners from runtime logins prevents apps from bypassing RLS accidentally.

### 35.2. FORCE ROW LEVEL SECURITY

```sql
ALTER TABLE shop_internal.tenant_orders
FORCE ROW LEVEL SECURITY;
```

When RLS is enabled, `FORCE` compels normal table owners to obey RLS policies as well—though superusers and `BYPASSRLS` still bypass.

### 35.3. Never Grant BYPASSRLS to Runtime Roles

A service login holding `BYPASSRLS` can read across tenants whenever table privileges permit. Never enable `BYPASSRLS` to patch over a missing policy.

### 35.4. Replication and RLS Are Orthogonal

Logical replication handles RLS differently from normal SQL queries, and physical WAL replication bypasses RLS completely. Track how data leaves the primary via replication even when SQL RLS looks airtight.

### 35.5. Never Trust Client-Supplied tenant_id GUCs

When RLS checks:

```sql
USING (
    tenant_id =
    current_setting('app.tenant_id')::INTEGER
)
```

ensure the variable is set solely by trusted server middleware without exposing arbitrary `SET` paths to clients.

---

## 36. Schema Segregation: Preventing Accidental Blanket Grants

Applications can split schemas by functional trust zone:

```text
shop_internal:
    customers, orders, payments, cost_data

shop_api:
    v_catalog, v_order_summary

shop_reports:
    v_daily_paid_orders, v_revenue_by_region

shop_staging:
    import_orders, import_errors
```

### 36.1. APIs Need USAGE Strictly on Required Schemas

```sql
GRANT USAGE ON SCHEMA shop_api TO shop_catalog_read;
```

with zero `USAGE` or `CREATE` on internal schemas.

### 36.2. Reporting Views Are Not Complete Masking by Default

To protect PII, inspect exposed columns, view ownership, `security_invoker`, RLS, helper functions, base grants, and downstream BI exports.

### 36.3. Isolate Raw Staging Schemas

ETL imports often stage uncleaned raw PII. Keep staging out of schemas readable by general reporting roles.

### 36.4. Per-Application vs. Per-Domain Owners

Depending on scale, use either one `app_owner` or separate domain owners. Keep trust boundaries clear and manageable inside migrations.

### 36.5. Excessive Role Sprawl Has Operational Cost

Over-splitting into hundreds of micro-roles complicates secret rotation, grant management, and audits. Group roles cleanly by equivalent privilege and sensitivity scope rather than creating one role per SQL query.

---

## 37. Replication and App Traffic Should Not Share Network Paths Unnecessarily

Even with separate logins, letting every role connect from anywhere keeps attack surface wide.

### 37.1. App Connections

```conf
# Example pg_hba.conf entries for application SQL traffic
hostssl   shopdb   catalog_api_login      10.20.10.0/24   scram-sha-256
hostssl   shopdb   inventory_worker_login 10.20.11.0/24   scram-sha-256
```

### 37.2. Physical Replication Connection

```conf
hostssl   replication   physical_repl_login   10.20.30.40/32   scram-sha-256
```

### 37.3. Logical Replication Connection

```conf
# Logical connections normally specify the actual database name
hostssl   shopdb   logical_repl_login   10.20.40.50/32   scram-sha-256
```

### 37.4. Never Rely Solely on pg_hba

Layer firewalls, TLS server verification, network segmentation, secret/cert lifecycle management, and connection logging.

### 37.5. On Managed PostgreSQL

Cloud providers often replace direct `pg_hba.conf` edits with VPC/firewall/control-plane APIs. Use provider mechanisms without assuming OS filesystem access.

---

## 38. Separate Credentials per Component

Clean credential separation versus one shared login:

```text
Catalog API        -> catalog_api_login       (secret A)
Inventory Worker   -> inventory_worker_login  (secret B)
Migration CI       -> shop_migration_login    (secret C)
Physical Standby   -> physical_repl_login     (secret D)
Logical Subscriber -> logical_repl_login      (secret E)
Monitoring         -> shop_monitor_login      (secret F)
```

### 38.1. Why Separate Secrets?

If Secret A leaks, you can revoke and rotate A cleanly without touching HA standbys, migrations, or analytics pipelines.

### 38.2. Same Role Names Across Environments?

Never reuse production passwords in dev or staging. Keeping role names consistent across environments simplifies migrations, provided secrets and memberships remain strictly isolated per environment.

### 38.3. Rotating Replication Credentials Requires Operational Coordination

Changing standby passwords/certificates can interrupt streaming if uncoordinated. Plan zero/minimal-lag dual-phase rollouts with rollback options.

### 38.4. Zero Secrets in Source Code

Never put real passwords in migration files, Git repos, CI stdout, or `SHOW` logs. Rely on secret managers, workload identities, or managed auth.

### 38.5. Credential Rotation Does Not Kill Already-Authenticated Sessions

Changing passwords or marking a role `NOLOGIN` blocks *new* logins while existing authenticated backends keep running. During incidents, terminate active sessions explicitly under DBA controls.

---

## 39. Monitoring Replication With Least-Privilege Observer Roles

Do not hand `physical_repl_login` credentials to monitoring dashboards just to graph lag.

### 39.1. pg_stat_replication

On primary, a role with suitable monitoring rights queries:

```sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_catalog.pg_stat_replication
ORDER BY application_name;
```

Visible columns and values depend on privileges and PostgreSQL version; certain fields may be `NULL`.

### 39.2. Replication Slots

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_catalog.pg_replication_slots
ORDER BY slot_name;
```

### 39.3. Logical Subscribers

On subscribers, inspect `pg_stat_subscription` to monitor apply workers and sync health per privileges and version.

### 39.4. Key Metrics to Track

- Send / write / flush / replay lag.
- Inactive replication slots.
- WAL retained per slot.
- Active WAL senders and connection failures.
- Time since last sync progress.
- Filesystem usage and growth rate.
- Auth, TLS, or permission denied errors.
- Subscription apply errors and worker restarts.

### 39.5. Monitoring Needs Less Privilege Than Replication

`pg_monitor` or a scoped monitoring role provides lag telemetry without needing `REPLICATION` privileges. Audit predefined roles carefully, as they still expose internal system details.

---

## 40. Auditing High-Privilege Roles

Inventory via `pg_roles`:

```sql
SELECT
    rolname,
    rolcanlogin,
    rolsuper,
    rolcreatedb,
    rolcreaterole,
    rolreplication,
    rolbypassrls
FROM pg_catalog.pg_roles
WHERE rolsuper
   OR rolcreaterole
   OR rolcreatedb
   OR rolreplication
   OR rolbypassrls
ORDER BY rolname;
```

### 40.1. Audit Questions

- Are any runtime logins `SUPERUSER`?
- Do any API logins hold `CREATEROLE` or `BYPASSRLS`?
- Which replication logins are still active vs. orphaned?
- Are break-glass `LOGIN` roles locked down and vault-managed?
- Do departed employee accounts still exist?
- Which provider-managed roles should remain untouched?

### 40.2. Never Judge Privileges From Names

A role named `read_only` with `rolsuper=true` is still a full superuser; a managed role named `admin` may not hold `rolsuper=true`.

### 40.3. Modifying Admin Roles Can Impact the Whole Cluster

Never execute `ALTER ROLE ... NOSUPERUSER` or `DROP ROLE` on critical admin accounts without a verified recovery path.

---

## 41. Auditing Default PUBLIC Grants

Two primary areas to inspect regularly:

### 41.1. Function EXECUTE

```sql
SELECT
    n.nspname AS schema_name,
    p.proname AS function_name,
    p.prosecdef AS security_definer,
    pg_catalog.pg_get_userbyid(p.proowner) AS owner
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = p.pronamespace
WHERE n.nspname IN ('shop_internal','shop_api')
ORDER BY n.nspname, p.proname;
```

Check effective ACLs with `has_function_privilege` or `aclexplode`, paying special attention to `prosecdef = true`.

### 41.2. The public Schema

```sql
SELECT
    pg_catalog.has_schema_privilege(
        'public', 'USAGE'
    ) AS current_role_can_use_public,
    pg_catalog.has_schema_privilege(
        'public', 'CREATE'
    ) AS current_role_can_create_in_public;
```

### 41.3. Defaults Vary Across Upgrades and Restores

PostgreSQL 15+ tightened `public` schema defaults on newly created databases, whereas upgraded clusters retain historical ACLs.

### 41.4. Never Issue Ad-Hoc REVOKEs in Live Shared Production

Blanket revocations of `CONNECT`/`CREATE`/`EXECUTE` can break live services instantly. Inventory dependencies, script migrations with rollbacks, and test in staging first.

---

## 42. Common Mistakes When Separating Roles

### 42.1. "Migration hit permission denied, so give it SUPERUSER"

Massively expands blast radius. Identify the missing owner/schema/grant/membership and fix only that duty.

### 42.2. "Runtime needs INSERT, so give it the owner role"

`INSERT` never requires ownership. Grant scoped table/column `INSERT`, sequence `USAGE`, plus constraints and RLS.

### 42.3. "Standby needs to stream, so reuse the admin password"

Dedicated `LOGIN REPLICATION` accounts work cleanly without sharing cluster superuser secrets.

### 42.4. "Analytics only replicates two tables, so the replication role is harmless"

Publications can change, initial sync reads tables, and subscribers still hold sensitive records. Keep replication roles separate from analyst query roles.

### 42.5. "REVOKE SELECT FROM PUBLIC is enough"

Roles may still retain `SELECT` via group memberships or direct grants. Audit effective privileges.

### 42.6. "We enabled RLS, so separating owners doesn't matter"

Table owners bypass RLS by default. Keep runtime logins separate from object ownership whenever RLS applies.

### 42.7. "Reader has no UPDATE grant, so it cannot mutate data"

It might still `EXECUTE` a write-capable `SECURITY DEFINER` function. Audit functions, memberships, and FDWs too.

### 42.8. "Replication lag is a permission issue—add BYPASSRLS"

Lag usually stems from network, slot stalls, CPU, write spikes, apply conflicts, or disk I/O. Never weaken security attributes to chase an unverified operational symptom.

---

## 43. Role Separation Across Primary and Multi-Replica Topologies

Consider a cluster layout:

```text
Primary shop-db
  |
  +--> Standby A (HA)
  +--> Standby B (read scaling)
  |
  +--> Logical subscriber analytics-db
  |
  +--> Backup service / WAL archive
  |
  +--> API applications
```

### 43.1. Should All Standbys Share One physical_repl_login?

While technically supported, assigning distinct logins per standby or partner (where manageable) improves rotation, auditing, and isolated revocation. Balance credential count against operational tooling.

### 43.2. Replication Roles Are Not Scoped Solely to One Named Slot

Depending on protocol privileges, a `REPLICATION` role may interact with replication beyond one app-configured slot name. Never rely on naming a slot alone as your security boundary.

### 43.3. Keep Physical and Logical Replication Credentials Separate

They serve distinct lifecycles, scopes, and failure domains. An analytics compromise must never force emergency rotation of HA physical standby credentials.

### 43.4. Separate Backup Logins From Standby Logins

Backups follow separate schedules, storage targets, and retention paths—use distinct backup identities even when both speak the replication protocol.

### 43.5. Monitoring Must Never Hold Subscription-Owner Privileges

Monitoring collects lag metrics; it never needs permission to create/drop subscriptions or modify connection strings.

---

## 44. Role Separation in Multi-Tenant Applications

Typical SaaS deployments combine:

- Multiple microservice logins.
- Multi-tenant tables keyed by `tenant_id`.
- RLS policies or server-enforced tenant scopes.
- Cross-tenant background workers with broader scope.
- Aggregate reporting pipelines distinct from per-tenant OLTP paths.

### 44.1. Each Microservice Forms Its Own Trust Boundary

Billing, support, and catalog handle distinct sensitivity levels. One shared `saas_runtime_all_access` role turns any minor catalog flaw into a billing breach.

### 44.2. Cross-Tenant Jobs Require Strict Review

A billing aggregation job spanning all tenants needs broader visibility than user APIs. Never blindly flip on `BYPASSRLS`; build narrow scoped views, policies, or audited worker roles instead.

### 44.3. Authenticate Tenant IDs Properly

If policies read `current_setting('app.tenant_id')`, ensure only trusted server layers set it cleanly with zero SQL paths letting callers spoof another tenant.

### 44.4. Multi-Tenant Logical Analytics Replicas Carry Full Sensitivity

If the analytics subscriber receives rows across every tenant, protect it as a sensitive multi-tenant store even if dashboards show aggregates.

### 44.5. Negative Multi-Tenant Tests Are Mandatory

Verify not only "tenant 10 reads tenant 10", but equally "tenant 10 cannot read or modify tenant 20" across every SQL/API path.

---

## 45. Incident Scenario: Catalog API Credential Compromised

Suppose `catalog_api_login` leaks.

### 45.1. With Proper Role Separation

The attacker can read only the catalog view/columns granted to that role, and cannot:

- Update stock counts.
- Drop or alter tables.
- Read unit costs or customer PII.
- Create subscriptions or stream WAL.
- Create or modify roles.
- Bypass RLS.

### 45.2. Response Steps

1. Identify the leaked login, affected environment, and reachable data scope.
2. Disable or rotate credentials immediately per runbook.
3. Terminate active sessions for the compromised login via authorized DBA commands.
4. Verify role attributes and memberships for unexpected drift.
5. Audit logs and query telemetry for data exfiltration.
6. Redeploy the service with fresh least-privilege secrets.
7. Audit all `SELECT`/`EXECUTE`/view paths for leftover over-permissions.

### 45.3. REVOKE Does Not Undo Past Data Exposure

Revoking access stops future queries; already-exfiltrated data still requires full breach investigation and response.

### 45.4. Distinguish Rotation From Session Termination

Changing a password or setting `NOLOGIN` blocks new logins while existing pooled connections remain alive until terminated explicitly. Plan graceful or forced termination carefully per availability impact.

### 45.5. Why Credential Separation Pays Off

Containment happens locally without forcing downtime across migrations, standbys, or backup jobs.

---

## 46. Incident Scenario: Migration Login Compromised

This carries broader blast radius than a runtime login.

### 46.1. Potential Impact

Because the migration role can `SET ROLE app_owner`, attackers can alter app-owned schemas, tables, `SECURITY DEFINER` functions, triggers, and runtime grants.

### 46.2. Why Keep Migration Secrets Out of Runtime Pods?

Putting migration credentials inside web pods expands their exposure surface to internet-facing APIs. Restrict them strictly to CI/CD runners, deployment operators, and secret vaults.

### 46.3. Operational Safeguards

- Require PR review and pipeline approvals.
- Execute migrations solely from trusted runners.
- Isolate secrets per environment.
- Scrub passwords from CI logs.
- Alert on unexpected DDL and `GRANT` edits.
- Protect migration artifact integrity.
- Maintain verified rollback/restore procedures.
- Rotate immediately on suspected exposure.

### 46.4. Migration Roles Still Never Need REPLICATION

Creating tables never requires streaming WAL or managing replication slots.

### 46.5. Security Belongs in Release Verification

A release with clean SQL logic that leaves objects owned by the wrong role or functions open to `PUBLIC EXECUTE` is still a security defect. Audit grants and owners post-migration automatically.

---

## 47. Incident Scenario: Replication Slot Retaining WAL Too Long

Suppose a logical subscriber stalls offline for hours while its slot pins WAL.

### 47.1. Symptoms

- Rising primary disk consumption.
- Slot `active = false` or `restart_lsn` stalled.
- Large replication lag.
- Storage saturation warnings.
- Primary writes risking downtime if disk fills completely.

### 47.2. Diagnostic Query

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_catalog.pg_replication_slots
ORDER BY slot_name;
```

Check consumer health, network connectivity, grants, publisher/subscriber versions, worker logs, and slot retention caps (`max_slot_wal_keep_size`).

### 47.3. Never Add SUPERUSER Because of Slot Lag

Slot stalls stem from operational or apply issues; escalating privileges never cures the root cause.

### 47.4. Restrict Slot Manipulation Privileges

Never let app runtimes arbitrarily create, drop, or advance replication slots unless explicitly part of their contract, as slot tampering threatens WAL retention and recovery.

### 47.5. Plan Consumer Re-Synchronization

If a slot must be dropped or WAL expires past retention, follow documented steps to re-seed the subscriber without corrupting downstream business or analytics data.

---

## 48. Role Offboarding and Privilege Revocation

When retiring a legacy deployment tool or microservice, decommission its role cleanly.

### 48.1. Audit Object Ownership

```sql
SELECT
    pg_catalog.pg_get_userbyid(c.relowner) AS owner,
    COUNT(*) AS relation_count
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname NOT IN ('pg_catalog','information_schema')
GROUP BY owner
ORDER BY relation_count DESC;
```

### 48.2. REASSIGN OWNED

```sql
REASSIGN OWNED BY old_owner TO new_owner;
```

Transfers ownership of objects in the current database across supported object types; verify privileges and repeat across every relevant database.

### 48.3. DROP OWNED

```sql
DROP OWNED BY old_owner;
```

Drops owned objects and revokes privileges granted to that role per PostgreSQL semantics. **Never run `DROP OWNED` just to "revoke a couple of GRANTs"**—it destroys objects owned by that role!

### 48.4. DROP ROLE

Drop roles only after clearing all ownerships, grants, and dependencies across every database in the cluster, and never drop replication roles actively serving standbys or subscriptions.

### 48.5. Revoking Group Memberships

When a login no longer requires a role group:

```sql
REVOKE shop_inventory_write FROM inventory_worker_login;
```

after impact review, while also checking direct grants and alternate memberships.

### 48.6. Managed and Predefined Roles

Never edit or drop PostgreSQL predefined roles or provider-managed roles arbitrarily; rely on official vendor tools with tested recovery plans.

---

## 49. Auditing Permissions via psql and SQL

Useful `psql` meta-commands:

```text
\du
\du+
\dn+
\dp shop_internal.*
\df+ shop_internal.*
```

Note these are `psql` client commands, not SQL executed over JDBC.

### 49.1. Role Attributes

```sql
SELECT rolname, rolsuper, rolcreaterole,
       rolreplication, rolbypassrls
FROM pg_catalog.pg_roles
ORDER BY rolname;
```

### 49.2. Schema Owners

```sql
SELECT nspname,
       pg_catalog.pg_get_userbyid(nspowner) AS owner
FROM pg_catalog.pg_namespace
ORDER BY nspname;
```

### 49.3. Privileged Functions

```sql
SELECT
    n.nspname,
    p.proname,
    pg_catalog.pg_get_userbyid(p.proowner) AS owner,
    p.prosecdef
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = p.pronamespace
WHERE p.prosecdef
ORDER BY n.nspname, p.proname;
```

### 49.4. Effective Privileges

```sql
SELECT
    pg_catalog.has_schema_privilege(
        'sec392_reader', 'sec392_lab', 'USAGE'
    ) AS schema_ok,
    pg_catalog.has_table_privilege(
        'sec392_reader', 'sec392_lab.v_catalog', 'SELECT'
    ) AS view_ok;
```

### 49.5. Current Effective Role

```sql
SELECT session_user, current_user;
```

Confirms which login initiated the session and whose privileges govern active SQL (remembering `current_user` shifts inside `SECURITY DEFINER` functions).

---

## 50. Automating Permission Verification in CI

CI pipelines should validate:

### 50.1. Schema Contract

- Tables belong strictly to intended `NOLOGIN` owners.
- Migration login can run required DDL.
- Runtime logins own zero tables.
- Sensitive schemas forbid `CREATE` for `PUBLIC`.
- Sensitive functions deny `PUBLIC EXECUTE`.
- View owners and security options match policy.

### 50.2. Positive Permission Tests

- Catalog API reads `v_catalog`.
- Inventory writer reads `sku`/`stock`.
- Inventory writer executes scoped `UPDATE stock` DML.
- Reporting services read permitted views.
- Replication connections authenticate cleanly with dedicated replication logins in staging.

### 50.3. Negative Permission Tests

- Catalog API cannot `UPDATE stock`.
- Catalog API cannot `SELECT unit_cost`.
- Inventory writer cannot `ALTER`/`DROP` tables.
- Runtime roles cannot `SET ROLE app_owner`.
- Runtime roles cannot `CREATE PUBLICATION` or `CREATE SUBSCRIPTION`.
- Runtime roles cannot connect over the replication protocol.
- Reporting roles cannot read out-of-scope PII tables.
- Tenant A cannot read or modify tenant B rows.

### 50.4. Isolate Each Expected Failure

Because a `permission denied` error aborts the current transaction, run negative assertions in separate transactions or connections with clean rollback handling so failures do not cascade across tests.

### 50.5. Re-Run After Every Migration

New tables may miss `GRANT`s for writers or inherit unwanted grants for readers; new `SECURITY DEFINER` routines can accidentally ship with `PUBLIC EXECUTE`. Catch grant drift in CI before production.

### 50.6. Never Run Disruptive Privilege Tests in Production

Creating `REPLICATION` roles, disconnecting standbys, or dropping subscriptions belongs in approved staging environments; production verification should favor read-only catalog checks and rollback-safe validation.

---

## 51. Infrastructure as Code and Migrations

PostgreSQL permissions should never exist solely as forgotten ad-hoc `GRANT` statements typed manually years ago.

### 51.1. Version-Control Your Role Matrix

Track explicitly:

```text
service / login / role group / database / schema /
object / privilege / justification / approving owner
```

Never store passwords or private keys inside the repository.

### 51.2. Provision Roles via Dedicated IaC Tools

Organizations often manage cluster roles and secrets via Terraform, Ansible, Kubernetes operators, or cloud IaC, while SQL migrations govern app schemas and object ACLs.

### 51.3. Pin Object Ownership Inside Migrations

Use `SET ROLE app_owner` or tightly controlled deploy wrappers so objects always belong to the intended owner.

### 51.4. Manage Default Privileges Explicitly

Version `ALTER DEFAULT PRIVILEGES` bound to the exact creator role rather than relying on one-off grants covering only present tables.

### 51.5. Audit Configuration Drift

Periodically compare live role attributes, memberships, grants, owners, and `SECURITY DEFINER` functions against the approved matrix.

### 51.6. Plan Rollbacks for Security Migrations

Overly tight `REVOKE`s break live traffic or replication; overly wide `GRANT`s leak data. Treat ACL changes with peer review, staging tests, and rollback scripts.

---

## 52. Right-Sizing Role Separation to System Scale

### 52.1. Small Applications

Can start cleanly with:

```text
admin
migration_login
app_owner NOLOGIN
app_runtime_login
dedicated backup/monitoring as needed
```

Even at small scale, `app_runtime` gets strictly required CRUD—never ownership or superuser.

### 52.2. Mid-Sized Systems

Split read/write logins, CI migrations, backups, physical standbys, logical analytics, and monitoring per infrastructure boundary.

### 52.3. Microservice Architectures

Give each service domain-specific roles (catalog, orders, billing, inventory) with zero cross-domain group memberships bridging privileges.

### 52.4. Multi-Tenant Platforms

Combine schema/role isolation with RLS, verified tenant contexts, forced owner rules where applicable, and replication exposure reviews.

### 52.5. High-Compliance Environments

Pair SQL `GRANT`/`REVOKE` with just-in-time elevated access, dual approvals, comprehensive audit trails, encryption, strict change management, and periodic access recertification.

### 52.6. No Single Matrix Fits Everyone

Balance least privilege with operational maintainability. If excessive complexity drives operators back to using superuser daily to unblock failures, simplify provisioning workflows while preserving core trust boundaries.

---

## 53. Common Misconceptions and Counterexamples

| Misconception | Reality |
| --- | --- |
| "The app just runs SELECT, so postgres login is fine." | Use a narrowly scoped runtime login |
| "Sharing one credential is simpler and still safe." | Maximizes blast radius and blocks clean rotation |
| "Migrations belong to the app, so reuse the runtime role." | Migrations need DDL; runtimes need strictly scoped DML |
| "Migrations require SUPERUSER." | Scoped owner/membership normally suffices |
| "Owner just means having GRANT ALL." | Ownership grants DDL, drop, and ACL control beyond grants |
| "A NOLOGIN owner holds no power." | Owns objects and activates via `SET ROLE` |
| "Giving runtime roles owner membership is harmless." | Lets runtime apps escalate via `SET ROLE` |
| "CREATEROLE, CREATEDB, and REPLICATION inherit like SELECT." | Special role attributes follow distinct rules |
| "GRANT ROLE always inherits everything automatically." | Inspect `INHERIT`/`SET`/`ADMIN` and PostgreSQL version |
| "Read-only roles don't need function audits." | `SECURITY DEFINER` functions can mutate data |
| "REPLICATION only reads a few tables." | Physical WAL covers the entire cluster |
| "Physical standbys require true superuser." | Dedicated `REPLICATION` login usually suffices |
| "Logical publications work just like table SELECT." | Publications/subscriptions have distinct privileges |
| "Initial logical sync doesn't need table SELECT." | Initial snapshot copies often require table `SELECT` |
| "Reuse the logical replication login for analytics BI." | Keep replication accounts separate from BI query roles |
| "FOR ALL TABLES only publishes current tables." | Automatically includes future newly created tables |
| "RLS filters physical WAL replication." | Physical replication bypasses SQL RLS |
| "Publication row filters provide full tenant isolation." | Carry limits; subscriber still requires hardening |
| "Grant BYPASSRLS to fix logical replication errors." | Tears down tenant isolation boundaries |
| "Naming one slot isolates a replication role to that slot." | Replication authority spans beyond a slot name |
| "max_wal_size guarantees slots never fill the disk." | Active/inactive slots pin WAL past `max_wal_size` |
| "Monitoring requires REPLICATION to watch lag." | Predefined monitoring roles inspect stats cleanly |
| "Backups work just like normal SELECT." | Physical and logical backups carry distinct scopes and permissions |
| "Schema USAGE grants table SELECT." | Distinct privilege layers |
| "GRANT ALL TABLES won't expose sensitive columns." | Exposes every column in matched tables |
| "GRANT UPDATE(stock) allows updating any column." | Restricted strictly to granted columns |
| "Writers without DROP or readers without UPDATE can't write." | Check `EXECUTE`, memberships, and ownership |
| "ALTER DEFAULT PRIVILEGES updates existing tables." | Affects future objects only |
| "Owner default grants apply even if migration skips SET ROLE." | Applies solely to the specified creator role |
| "public always grants CREATE to PUBLIC." | Defaults tightened in PG 15+ for new DBs |
| "REVOKE FROM PUBLIC strips every role's access." | Direct and group-inherited grants remain active |
| "Changing a password kills open connections immediately." | Existing sessions continue until closed or terminated |
| "pg_hba hostssl authenticates the server to clients." | Clients must still validate certs/hostnames (`verify-full`) |
| "IP allowlists alone are enough." | Also protect secrets, TLS verification, and firewalls |
| "Managed cloud admin always has rolsuper=true." | Cloud providers routinely restrict true superuser |
| "Testing permissions as superuser proves runtime limits." | Superusers bypass limits; test as real runtime roles |
| "Only positive functional tests matter." | Negative tests prove security boundaries hold |
| "Restoring data automatically restores identical security." | Owners, grants, RLS, and roles can diverge |
| "DROP OWNED just cleans up a few grants." | Drops every object owned by that role |
| "More roles is always better." | Balance least privilege against operational clarity |
| "Grant edits can go straight to prod without staging." | Risks outages or accidental data leaks |
| "RLS using an unchecked session variable is secure." | Tenant context must be authenticated and tamper-proof |
| "Sharing replication logins with web apps is convenient." | Violates trust boundaries with huge blast radius |

---

## 54. Practice Exercises

### Exercise 1 — Identifying Blast Radius

A catalog service connects as superuser. List at least five consequences if SQL injection occurs, compared against granting strictly `SELECT` on `v_catalog`.

### Exercise 2 — Role Matrix

Build a role matrix covering admin, migration, app read, app write, physical replication, logical replication, backup, and monitoring—indicating `LOGIN` vs `NOLOGIN` and prohibited privileges.

### Exercise 3 — NOLOGIN Owner

Create a `NOLOGIN` owner and a schema owned by it. Explain why the owner needs no login password for application traffic.

### Exercise 4 — Runtime Does Not Own Tables

Create a table as the owner role, then `GRANT SELECT` to a runtime reader. Verify the reader cannot `DROP` the table.

### Exercise 5 — LOGIN vs NOLOGIN

Create a `NOLOGIN` group role and a `LOGIN` role in a lab. Explain how `NOLOGIN` groups can still own objects and hold privileges.

### Exercise 6 — Membership

Grant a group role to a runtime role and inspect effective privileges. If the runtime role joins another group, do privileges accumulate?

### Exercise 7 — SET ROLE

Switch an authorized migration login to the owner role, then `RESET ROLE`. Query `session_user` and `current_user` before and after.

### Exercise 8 — Blocking Runtime SET ROLE to Owner

Write a negative test proving runtime logins cannot switch to the owner role. If it succeeds unexpectedly, what should you audit?

### Exercise 9 — PostgreSQL 16 Membership Options

Explain `ADMIN`, `INHERIT`, and `SET` membership options. Why can't `rolinherit` alone determine every escalation path?

### Exercise 10 — Superuser

Why do routine table-creation migrations never require superuser? Which genuine tasks require cluster admin privileges?

### Exercise 11 — Role Attributes Audit

Write a query listing every role with `SUPERUSER`, `CREATEROLE`, `CREATEDB`, `REPLICATION`, or `BYPASSRLS`. What signals warrant immediate review if spotted on runtime roles?

### Exercise 12 — CREATEDB vs CREATE ON DATABASE

Compare both privileges. Why must neither be granted to a catalog API?

### Exercise 13 — BYPASSRLS

A multi-tenant API depends on RLS, yet its login carries `BYPASSRLS`. Trace how cross-tenant leakage occurs.

### Exercise 14 — Owner and RLS

Create an RLS-enabled table in a lab. Compare queries run as the table owner versus a policy-restricted runtime role, then test `FORCE ROW LEVEL SECURITY` where permitted.

### Exercise 15 — Schema USAGE

Grant `USAGE ON SCHEMA` to a reader without table `SELECT`. Explain the error and apply minimal grants.

### Exercise 16 — Column GRANT

Grant `SELECT (sku, stock)` while withholding `unit_cost`. Write positive and negative `SELECT` tests to verify.

### Exercise 17 — Catalog View

Create `v_catalog` exposing `sku`, `display_name`, and `stock`, granting view `SELECT`. Why must you still audit base-table grants?

### Exercise 18 — Narrow Writer

Grant `SELECT (sku, stock)` and `UPDATE (stock)` to a writer. Test updating `stock` inside a rolled-back transaction, then attempt updating `unit_cost` and explain the denial.

### Exercise 19 — GRANT ALL Is Overly Broad

For an inventory worker adjusting only stock, list the excessive grants introduced by `GRANT ALL ON TABLE products`.

### Exercise 20 — Default Privileges

Configure an owner role so future tables created in a reporting schema grant `SELECT` to `report_reader`. Why don't existing tables inherit the new ACL automatically?

### Exercise 21 — Creator Drift

A migration omits `SET ROLE owner` and creates tables as `migration_login`. Explain the consequences for ownership, ACLs, and future releases.

### Exercise 22 — Existing vs Future Grants

Write SQL granting permissions on existing reporting tables alongside `ALTER DEFAULT PRIVILEGES` for future tables when authorized by policy.

### Exercise 23 — PUBLIC EXECUTE

After creating a new `SECURITY DEFINER` function, what action is required regarding default `PUBLIC` execution grants?

### Exercise 24 — Indirect Write via Function

A role lacks table `UPDATE` yet holds `EXECUTE` on a `SECURITY DEFINER` function that runs `UPDATE`. Is the role truly "read-only"?

### Exercise 25 — search_path

Describe object shadowing risks inside `SECURITY DEFINER`. Why combine schema-qualified names with a pinned trusted `search_path`?

### Exercise 26 — Physical Replication

Why does a physical standby require a `REPLICATION` role rather than `GRANT SELECT ON ALL TABLES`?

### Exercise 27 — WAL Confidentiality

RLS restricts an API to tenant 10. Does RLS restrict a physical replication role to tenant 10 WAL records? Explain.

### Exercise 28 — Physical pg_hba

Write a `hostssl replication ...` rule permitting strictly one standby IP. Why avoid `0.0.0.0/0`?

### Exercise 29 — TLS and Certificates

Explain why `hostssl` still requires client-side certificate and hostname verification to stop server impersonation.

### Exercise 30 — Replication Parameters

Run `SHOW wal_level`, `max_wal_senders`, and `max_replication_slots`. Explain why these control capacity without granting `REPLICATION` privileges.

### Exercise 31 — Physical Backup

Which attributes might a `pg_basebackup` job need, and why must web API logins never share them?

### Exercise 32 — Logical Publication

Design a publication exposing two analytics tables. Why does `FOR ALL TABLES` risk unintended exposure?

### Exercise 33 — Logical Initial Sync

A logical subscriber hits `permission denied` during initial snapshot copy. Which publisher privileges must be inspected?

### Exercise 34 — Logical vs Physical

Compare both replication modes across data scope, DDL handling, RLS behavior, and role privileges.

### Exercise 35 — Separate Subscriber Privileges

Why should subscription ownership and config on `analytics-db` remain isolated from HTTP app logins?

### Exercise 36 — Connection String Secrets

A SQL migration embeds a plain replication password. List leak vectors and show how to harden the workflow.

### Exercise 37 — Row Filters and Tenants

Suppose a publication row filter targets certain tenants. Why check initial sync, `UPDATE`/`DELETE`, `REPLICA IDENTITY`, and subscriber hardening instead of relying solely on the filter?

### Exercise 38 — Replication Slot Retention

A logical slot sits inactive for days. What metrics indicate trouble, and why doesn't `max_wal_size` stop disk exhaustion?

### Exercise 39 — Avoid Blindly Dropping Slots

If a slot is dropped while its consumer still relies on retained WAL, what breaks? Outline a safe incident decision workflow.

### Exercise 40 — Narrow Monitoring Role

A dashboard needs only replication lag. Why choose a scoped monitoring role over a `REPLICATION` login?

### Exercise 41 — pg_stat_replication

Query `application_name`, `state`, `sync_state`, `sent_lsn`, `write_lsn`, `flush_lsn`, and `replay_lsn`, explaining each stage.

### Exercise 42 — pg_replication_slots

Query `slot_type`, `active`, `restart_lsn`, and `confirmed_flush_lsn`. Which columns can be `NULL` per slot type?

### Exercise 43 — Auditing pg_roles

Write a query scanning `pg_roles` to flag any runtime login holding unexpected `rolsuper`, `rolbypassrls`, or `rolreplication`.

### Exercise 44 — Auditing Memberships

Query `pg_auth_members` to list role-to-role grants; explain why paths reaching owner roles create danger.

### Exercise 45 — Privilege Helper Functions

Use `has_schema_privilege`, `has_table_privilege`, and `has_column_privilege` to prove the lab reader holds strictly required permissions.

### Exercise 46 — Password Rotation

Design a zero/minimal-disruption rotation plan for physical replication credentials. Which metrics should be watched?

### Exercise 47 — Terminating Active Sessions

After setting `ALTER ROLE app_login NOLOGIN` following a leak, why inspect active sessions and who may terminate them?

### Exercise 48 — Compromised Migration Role

Analyze blast radius if a migration credential able to `SET ROLE app_owner` (though non-`SUPERUSER`) leaks. Which assets remain exposed?

### Exercise 49 — Multi-Tenant Role Architecture

Design roles for catalog, billing, support, inventory, and analytics. What should each receive, and why avoid merging them into a shared `SELECT`-everything group?

### Exercise 50 — RLS Tenant Context

A policy checks `current_setting('app.tenant_id')` writable by SQL callers. Explain why this fails as verified tenant isolation.

### Exercise 51 — Post-Restore ACL Checks

After restoring with flags omitting owners or grants, what must be verified before letting applications reconnect?

### Exercise 52 — Offboarding

A deprecated deploy role owns views and holds grants across multiple databases. Plan `REASSIGN OWNED`, `DROP OWNED`, and `DROP ROLE` safely.

### Exercise 53 — CI Negative Tests

List at least eight actions runtime roles must fail: `ALTER`, `DROP`, reading PII, updating cost, `SET ROLE owner`, role admin, `REPLICATION`, and cross-tenant reads.

### Exercise 54 — Production Architecture Design

A cluster spans a primary, two physical standbys, one logical analytics subscriber, three microservices, CI migrations, monitoring, and backups. Diagram all roles, logins, grants, secrets, network/TLS boundaries, plus testing, rotation, recovery, ownership control, and drift detection.

---

## 55. Role Separation Implementation Checklist

| Question | What to Verify |
| --- | --- |
| Documented role matrix? | Admin / migration / owner / app / replication / backup / monitor |
| Do runtime roles use superuser? | No |
| Do runtime roles hold `CREATEROLE`/`CREATEDB`? | No unless strictly needed |
| Do runtime roles hold `REPLICATION`? | No |
| Do runtime roles hold `BYPASSRLS`? | No in multi-tenant apps |
| Is the owner role `NOLOGIN`? | Yes wherever supported |
| Separate credentials for migrations and apps? | Yes |
| Are break-glass accounts avoided in daily use? | Yes |
| Can runtime memberships reach the owner role? | No |
| Evaluated `INHERIT`/`SET`/`ADMIN` options? | Aligned with PostgreSQL version |
| Verified `current_user` and `session_user`? | Checked in tests |
| Scoped schema `USAGE` for apps? | Required schemas only |
| Extra schema `CREATE` rights on apps? | No |
| Exact table and column grants? | Minimum needed `SELECT`/`INSERT`/`UPDATE`/`DELETE` |
| Unnecessary `DELETE`/`TRUNCATE` rights? | Revoked |
| Sequence privileges reviewed? | Matching `DEFAULT nextval` / identity behavior |
| Sensitive functions exposed to `PUBLIC EXECUTE`? | No |
| `SECURITY DEFINER` routines audited? | Owner, `search_path`, body, injection, inputs, grants |
| RLS applied to tenant tables? | Aligned with policy |
| Do runtime logins own tables? | No when RLS applies |
| Audited owner bypass and `FORCE RLS`? | Yes |
| Verified tamper-proof tenant context? | Never trust raw client inputs |
| Audited view owners and `security_invoker`? | Yes |
| Migrations create objects under exact owner? | Verified via `SET ROLE` / memberships |
| Default privileges bound to true creator role? | Yes |
| Covered both existing and future tables? | Managed separately |
| Audited `public` schema grants? | Verified for version and upgrade history |
| Audited role attributes? | `pg_roles` |
| Audited role memberships? | `pg_auth_members` |
| Audited object ownership? | `pg_namespace` / `pg_class` / `pg_proc` |
| Evaluated effective privileges? | `has_*_privilege` |
| Executed negative permission tests? | Run as realistic runtime roles |
| Dedicated physical replication role? | Yes |
| Dedicated logical replication role? | Yes when used |
| Dedicated backup account? | Scoped per backup tool |
| Dedicated monitoring role? | Needs no `REPLICATION` by default |
| HBA rules restrict physical replication by IP? | Yes |
| Logical HBA rules target exact database? | Matches connection contract |
| TLS verifies client/server identities? | Yes |
| Connection string secrets protected? | Never hard-coded or logged |
| Audited initial logical sync `SELECT` rights? | Yes |
| Reviewed publication table/column/row scope? | Strictly minimal |
| Audited subscriber tables, ACLs, and owners? | Yes |
| Tested RLS and logical apply interactions? | Yes |
| Monitored replication slots? | `active`, `restart_lsn`, retained WAL |
| Alerting on disk and WAL growth? | Yes |
| Tested replication credential rotation plan? | Minimizes HA interruption |
| Audited access to backups and WAL archives? | Yes |
| Practiced restore drills including ACL verification? | Owners, grants, RLS, logins |
| Documented role offboarding workflow? | Multi-DB reassign/cleanup |
| Active session handling after revocations? | Terminated cleanly per runbook |
| Environment separation across dev/staging/prod secrets? | Yes |
| Resource limits on reader roles? | Statement timeouts and pool caps |
| Migration PR reviews and approvals? | Yes |
| Automated privilege drift monitoring? | Yes |
| Incident response playbook ready? | Isolate, rotate, audit, recover |
| Documented ownership and approval contacts? | Named owner per role |

---

## 56. Conclusion

**Separating administrative, migration, replication, and application roles** is not busywork to invent tidy account names—it turns **least privilege** into testable, enforceable security boundaries with clean recovery paths during incidents.

Core principles to remember:

1. **Cluster administration differs from schema management.** Reserve superuser/break-glass strictly for rare top-tier operations; run migrations under controlled owner roles.
2. **Migrations differ from runtime traffic.** HTTP services must never carry `ALTER`/`DROP` authority or CI/CD credentials.
3. **`NOLOGIN` owners create strong isolation.** They hold object ownership while runtime logins hold strictly scoped `SELECT`/DML.
4. **Role memberships carry real privilege power.** Never let runtime logins `SET ROLE` into owners, and understand version-specific `INHERIT`/`SET`/`ADMIN` semantics.
5. **Grant application access by functional duty.** Catalog readers, order writers, inventory workers, and BI tools need distinct boundaries.
6. **Physical replication is high-privilege.** WAL and base backups span entire clusters, bypassing API views and column filters.
7. **Logical replication has narrower scope yet stays sensitive.** Coordinate publisher, publication, initial sync, subscription, subscriber, and RLS cleanly.
8. **Replication slots govern availability.** Stalled consumers pin WAL until disks fill; monitor and manage slots without reckless deletion.
9. **Keep backups and monitoring separate from apps and replication.** Use purpose-built roles matching exact tooling requirements.
10. **Default privileges and creator roles dictate future ACLs.** Verify every migration to stop owner drift and accidental broad grants.
11. **RLS and `SECURITY DEFINER` never replace clean role separation.** Over-privileged roles or poorly written routines bypass row rules effortlessly.
12. **Testing what is denied matters as much as testing what works.** Ask not only "does the API work?", but equally "what is the API proven unable to do?".
13. **Privileges have a full lifecycle.** Credential vaults, TLS, rotation, session cleanup, auditing, backup/restore drills, and offboarding are mandatory.
14. **Least privilege requires continuous upkeep.** Services, schemas, publications, and permissions evolve—monitor drift relentlessly.

A well-architected PostgreSQL cluster lets every service fulfill its duty cleanly—and ensures that if any single component fails or is compromised, **it never becomes a free pass to administer the cluster, alter schemas, or exfiltrate the entire database**. That is the practical payoff of strict role separation.
